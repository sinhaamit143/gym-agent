import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import html2pdf from 'html2pdf.js';
import ReactMarkdown from 'react-markdown';

interface Thought {
  node: string;
  text: string;
}

interface Message {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  thoughts: Thought[];
  isThinking: boolean;
  lastNode?: string;
}

// UI form removed down to chat only
const ThoughtProcess = ({ thoughts, isThinking }: { thoughts: Thought[], isThinking: boolean }) => {
  const [expanded, setExpanded] = useState(false);

  if (thoughts.length === 0 && !isThinking) return null;

  return (
    <div className="thought-process-container">
      <div 
        className={`thought-header ${expanded ? 'expanded' : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        {isThinking ? (
           <><span className="spinner"></span> <span>Virtual Staff Orchestrating...</span></>
        ) : (
           <><span className="thought-icon">🧠</span> <span>View Background Planning</span></>
        )}
        <span className={`caret ${expanded ? 'expanded' : ''}`}>▼</span>
      </div>
      {expanded && (
        <div className="thought-content">
          {thoughts.map((t, idx) => (
             <div key={idx} className="thought-node">
               <div className="thought-node-name">{t.node.replace('_', ' ')} Agent</div>
               <div dangerouslySetInnerHTML={{ __html: t.text.replace(/\n/g, '<br/>') }} />
             </div>
          ))}
          {thoughts.length === 0 && isThinking && <div>Loading models...</div>}
        </div>
      )}
    </div>
  );
}

const ActionPanel = ({ 
  msg,
  threadId,
  onApprove,
  onManual
}: { 
  msg: Message,
  threadId: string,
  onApprove: () => void,
  onManual: (text: string) => void
}) => {
  const [email, setEmail] = useState('');
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const [feedback, setFeedback] = useState({ name: '', phone: '', comment: '' });
  const [sendingFeedback, setSendingFeedback] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  if (msg.isThinking) return null;

  const handleDownloadPDF = () => {
    const element = document.createElement('div');
    element.innerHTML = `
      <div style="font-family: sans-serif; padding: 30px; color: #111; line-height: 1.6;">
        <h1 style="color: #000; border-bottom: 2px solid #eaeaea; padding-bottom: 10px;">Your Custom Protocol</h1>
        <p style="color: #666; font-size: 11px;">Thread Reference: ${threadId}</p>
        <div style="margin-top: 30px;">${msg.content.replace(/\n/g, '<br/>')}</div>
      </div>
    `;
    const opt = {
      margin: 0.5,
      filename: `Protocol-${threadId}.pdf`,
      image: { type: 'jpeg' as const, quality: 0.98 },
      html2canvas: { scale: 2 },
      jsPDF: { unit: 'in' as const, format: 'letter' as const, orientation: 'portrait' as const }
    };
    html2pdf().set(opt).from(element).save();
  };

  const handleSendEmail = async () => {
    if (!email) return;
    setSendingEmail(true);
    try {
      await fetch('/api/send-email', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ email, content: msg.content })
      });
      setEmailSent(true);
    } catch(e) {
      console.error(e);
    } finally {
      setSendingEmail(false);
    }
  };

  const handleFeedback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedback.name || !feedback.comment) return;
    setSendingFeedback(true);
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ ...feedback, thread_id: threadId })
      });
      setFeedbackSent(true);
    } catch(e) {
      console.error(e);
    } finally {
      setSendingFeedback(false);
    }
  };

  // Clarify interactions are now handled strictly through conversational inputs
  if (msg.lastNode === 'ask_approval') {
    return (
      <div className="action-panel">
        <p className="action-hint">The protocol has been drafted. We need your go-ahead to finalize it.</p>
        <button onClick={onApprove} className="approve-btn">Authorize Protocol</button>
      </div>
    );
  }

  if (msg.lastNode === 'manager') {
    return (
      <div className="action-panel final-actions">
        <h4>Save & Export</h4>
        <div className="export-actions">
          <button onClick={handleDownloadPDF} className="export-btn">📄 Save as PDF</button>
          <div className="email-row">
            <input 
              type="email" 
              placeholder="Delivery Email..." 
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <button onClick={handleSendEmail} disabled={sendingEmail || emailSent} className="export-btn">
               {emailSent ? 'Sent' : 'Send'}
            </button>
          </div>
        </div>

        <div className="feedback-section">
          <h4>Adjustments or Feedback</h4>
          {feedbackSent ? (
            <p className="success-msg">Received. Revisions are queued to the manager.</p>
          ) : (
            <form onSubmit={handleFeedback} className="feedback-form">
              <input type="text" placeholder="Full Name" value={feedback.name} onChange={e=>setFeedback({...feedback, name:e.target.value})} required/>
              <textarea placeholder="Tell us what needs changing..." value={feedback.comment} onChange={e=>setFeedback({...feedback, comment:e.target.value})} required/>
              <button type="submit" disabled={sendingFeedback} className="submit-btn">{sendingFeedback ? 'Routing...' : 'Submit to Management'}</button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return null;
}

interface ThreadInfo {
  id: string;
  title: string;
}

function AuthScreen({ onLogin }: { onLogin: (email: string) => void }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    const endpoint = isLogin ? '/api/login' : '/api/register';
    
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication Failed");
      onLogin(email);
    } catch(err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-layout" data-theme="dark">
      <div className="auth-container">
        <h1>Welcome to Fitness AI</h1>
        <p>{isLogin ? 'Sign in to access your workout plans.' : 'Create an account to get started.'}</p>
        
        <form onSubmit={handleSubmit} className="auth-form">
          <input type="email" placeholder="Email Address" value={email} onChange={e=>setEmail(e.target.value)} required/>
          <input type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} required/>
          {error && <div style={{color:'#ef4444', fontSize:'0.9rem'}}>{error}</div>}
          <button type="submit" disabled={loading}>{loading ? 'Processing...' : (isLogin ? 'Sign In' : 'Register')}</button>
        </form>
        
        <button onClick={() => setIsLogin(!isLogin)} className="toggle-auth">
          {isLogin ? "Don't have an account? Sign up" : "Already have an account? Log in"}
        </button>
      </div>
    </div>
  );
}

const MessageRow = React.memo(({ msg, threadId, handleManualSubmit, messagesEndRef }: any) => {
  return (
    <div className={`message-wrapper ${msg.role}`}>
      <div className="message-bubble">
        {msg.role === 'assistant' && (msg.thoughts.length > 0 || msg.isThinking) && (
          <ThoughtProcess thoughts={msg.thoughts} isThinking={msg.isThinking} />
        )}
        {msg.content && (
          <div className="markdown-body">
             <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        )}

        {msg.role === 'assistant' && msg.id === messagesEndRef && (
          <ActionPanel 
             msg={msg} 
             threadId={threadId} 
             onApprove={() => handleManualSubmit('I approve!')} 
             onManual={handleManualSubmit} 
          />
        )}
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Deep-check the message parameters to bypass function memory rewrites, completely stabilizing React's DOM!
  return prevProps.msg.content === nextProps.msg.content && 
         prevProps.msg.isThinking === nextProps.msg.isThinking && 
         prevProps.msg.thoughts.length === nextProps.msg.thoughts.length &&
         prevProps.msg.lastNode === nextProps.msg.lastNode;
});

const AdminDashboard = ({ onBack }: { onBack: () => void }) => {
  const [metrics, setMetrics] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/admin/dashboard-stats')
      .then(r => r.json())
      .then(d => {
        setMetrics(d.metrics || []);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setLoading(false);
      });
  }, []);

  return (
    <div className="admin-dashboard">
      <div className="admin-header">
         <h2>Admin Insights Dashboard</h2>
         <button className="logout-btn" onClick={onBack}>Back to Chat</button>
      </div>
      <div className="admin-content">
        {loading ? (
           <div className="loader-indicator" style={{justifyContent: 'center', marginTop: '3rem'}}>
              <span className="dot"></span><span className="dot"></span><span className="dot"></span>
              <span style={{marginLeft: '8px'}}>Aggregating platform metrics...</span>
           </div>
        ) : (
           <table className="admin-table">
             <thead>
               <tr>
                 <th>Customer Email</th>
                 <th>Total Threads</th>
                 <th>Coach Plans (Created)</th>
                 <th>Diet Plans (Created)</th>
                 <th>Manager Approvals</th>
               </tr>
             </thead>
             <tbody>
               {metrics.map(m => (
                 <tr key={m.customer}>
                   <td>{m.customer}</td>
                   <td>{m.total_threads}</td>
                   <td>{m.coach_plans}</td>
                   <td>{m.nutritionist_plans}</td>
                   <td>{m.manager_approvals}</td>
                 </tr>
               ))}
               {metrics.length === 0 && (
                 <tr>
                   <td colSpan={5} style={{textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)'}}>No advanced metrics found yet.</td>
                 </tr>
               )}
             </tbody>
           </table>
        )}
      </div>
    </div>
  );
};

function App() {
  const [user, setUser] = useState<string | null>(localStorage.getItem('gym-user'));
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [currentView, setCurrentView] = useState<'chat' | 'admin'>('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const savedTheme = localStorage.getItem('app-theme') as 'light' | 'dark';
    if (savedTheme) {
       setTheme(savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
       setTheme('dark');
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    localStorage.setItem('app-theme', newTheme);
  };

  const handleLogin = (email: string) => {
    setUser(email);
    localStorage.setItem('gym-user', email);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('gym-user');
    setMessages([]);
  };

  // Re-run thread initialization whenever user logs in
  useEffect(() => {
    if (user) {
      handleNewChat();
      fetchThreads();
    }
  }, [user]);

  const fetchThreads = async () => {
    if (!user) return;
    const safePrefix = user.replace(/[^a-zA-Z0-9]/g, '');
    try {
      const res = await fetch(`/api/history?email=${encodeURIComponent(safePrefix)}`);
      if (res.ok) {
        const data = await res.json();
        setThreads(data.threads);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadThread = async (tId: string) => {
    setCurrentThreadId(tId);
    setMessages([]);
    setIsTyping(true);
    setIsSidebarOpen(false);
    try {
      const res = await fetch(`/api/history/${tId}`);
      if (res.ok) {
         const data = await res.json();
         const loadedMsgs: Message[] = data.messages.map((m: any, idx: number) => ({
          id: `loaded-${idx}`,
          role: m.role,
          content: m.content,
          thoughts: [],
          isThinking: false
         }));
         setMessages(loadedMsgs);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsTyping(false);
    }
  };

  const handleNewChat = () => {
    if (!user) return;
    setCurrentThreadId(`${user.replace(/[^a-zA-Z0-9]/g, '')}-${Date.now()}`);
    setMessages([]);
    setIsSidebarOpen(false);
  };

  const handleManualSubmit = (overrideText: string) => {
    if (isTyping) return;
    executeMessage(overrideText);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;
    const userMsg = input.trim();
    setInput('');
    executeMessage(userMsg);
  };

  const executeMessage = async (userMsg: string) => {
    const userMessage: Message = { id: Date.now(), role: 'user', content: userMsg, thoughts: [], isThinking: false };
    
    setIsTyping(true);
    setMessages(prev => [...prev, userMessage]);

    const assistantId = Date.now() + 1;
    const initialAssistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      thoughts: [],
      isThinking: true
    };

    setMessages(prev => [...prev, initialAssistantMsg]);

    try {
      const response = await fetch('/api/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userMsg, thread_id: currentThreadId })
      });

      if (!response.body) throw new Error('No response body');
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let currentEvent = 'message';
      let activeNode = '';
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        let match = buffer.match(/\r?\n\r?\n/);
        while (match && match.index !== undefined) {
          const boundary = match.index;
          const matchLength = match[0].length;
          
          const messageChunk = buffer.substring(0, boundary);
          buffer = buffer.substring(boundary + matchLength);
          
          currentEvent = 'message'; // Safely reset event frame
          const lines = messageChunk.split(/\r?\n/);
          
          for (let line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              const dataStr = line.replace('data:', '').trim();
              
              // End events must process unconditionally before dataStr checks throw out empty buffers
              if (currentEvent === 'end' || currentEvent === 'error') {
                 setMessages(prev => {
                    const newMessages = [...prev];
                    const msgIndex = newMessages.findIndex(m => m.id === assistantId);
                    if (msgIndex !== -1) {
                       newMessages[msgIndex] = { ...newMessages[msgIndex], isThinking: false };
                    }
                    return newMessages;
                 });
                 setIsTyping(false);
                 continue;
              }

              if (!dataStr) continue;
              
              if (currentEvent === 'agent_change') {
                 activeNode = dataStr;
              } else if (currentEvent === 'message') {
               try {
                 const dataObj = JSON.parse(dataStr);
                 if (dataObj.token !== undefined) {
                   const token = dataObj.token;
                   
                   setMessages(prev => {
                     const newMessages = [...prev];
                     const msgIndex = newMessages.findIndex(m => m.id === assistantId);
                     if (msgIndex === -1) return newMessages;
                     
                     const msg = { ...newMessages[msgIndex] };
                     newMessages[msgIndex] = msg;
                     msg.lastNode = activeNode;
                     msg.isThinking = false;
                     msg.content += token; // Force all text onto the screen natively
                     
                     // Keep background planning accordion synced
                     if (!['greeter'].includes(activeNode)) {
                         const thoughts = [...msg.thoughts];
                         msg.thoughts = thoughts;
                         if (thoughts.length === 0 || thoughts[thoughts.length - 1].node !== activeNode) {
                            thoughts.push({ node: activeNode, text: token });
                         } else {
                            thoughts[thoughts.length - 1].text += token;
                         }
                     }
                     
                     return newMessages;
                   });
                 }
               } catch(ex) {}
              }
            }
          }
          match = buffer.match(/\r?\n\r?\n/);
        }
      }
      
      fetchThreads();
    } catch (error) {
      console.error(error);
      setIsTyping(false);
    } finally {
      setIsTyping(false);
      setMessages(prev => {
        const newMessages = [...prev];
        const msgIndex = newMessages.findIndex(m => m.id === assistantId);
        if (msgIndex !== -1) {
           newMessages[msgIndex] = { ...newMessages[msgIndex], isThinking: false };
        }
        return newMessages;
     });
    }
  };

  if (!user) {
    return <AuthScreen onLogin={handleLogin} />;
  }

  return (
    <div className="app-layout" data-theme={theme}>
      <aside className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-title-row">
             <h2>Log</h2>
             <button className="close-sidebar-btn" onClick={() => setIsSidebarOpen(false)}>×</button>
          </div>
          <button className="new-chat-btn" onClick={() => { setCurrentView('chat'); handleNewChat(); }}>
            <span style={{ fontSize: '1.2rem', lineHeight: 0 }}>+</span> New Session
          </button>
          <button className="new-chat-btn" onClick={() => setCurrentView('admin')} style={{ marginTop: '0', background: 'var(--thought-bg)' }}>
            📊 Admin Dashboard
          </button>
        </div>
        <div className="thread-list">
          {threads.map(t => (
            <div 
              key={t.id} 
              className={`thread-item ${t.id === currentThreadId && currentView === 'chat' ? 'active' : ''}`}
              onClick={() => { setCurrentView('chat'); loadThread(t.id); }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.6">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              {t.title}
            </div>
          ))}
          {threads.length === 0 && (
            <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              No history found natively.
            </div>
          )}
        </div>
      </aside>

      {currentView === 'admin' ? (
         <AdminDashboard onBack={() => setCurrentView('chat')} />
      ) : (
      <div className="app-container">
        <header className="header">
          <button className="menu-toggle-btn" onClick={() => setIsSidebarOpen(true)}>☰</button>
          <div className="header-center" style={{ flex: 1, position: 'relative' }}>
            <h1>Fitness AI</h1>
          </div>
          <div style={{display:'flex', gap:'1rem', alignItems:'center'}}>
             <button onClick={toggleTheme} className="theme-toggle" aria-label="Toggle Theme">
                {theme === 'light' ? '☾' : '☼'}
             </button>
             <button onClick={handleLogout} className="logout-btn">Sign Out</button>
          </div>
        </header>
        
        <main className="chat-container">
          <div className="messages-wrapper">
            <div className="messages-area">
              {messages.length === 0 && (
                 <div className="empty-state">
                   <h2>Good to see you, {user.split('@')[0]}</h2>
                   <p>Set a goal to begin.</p>
                 </div>
              )}
              
              {messages.map((msg, index) => (
                 <MessageRow 
                    key={msg.id} 
                    msg={msg} 
                    threadId={currentThreadId} 
                    handleManualSubmit={handleManualSubmit}
                    messagesEndRef={index === messages.length - 1 ? msg.id : null}
                 />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>
          
          <div className="input-container">
            {isTyping && (
              <div className="loader-indicator">
                <span className="dot"></span>
                <span className="dot"></span>
                <span className="dot"></span>
                <span>Generating response...</span>
              </div>
            )}
            <form onSubmit={handleSubmit} className="input-form">
              <input 
                type="text" 
                placeholder="Message Fitness AI..." 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isTyping}
              />
              <button type="submit" disabled={isTyping || !input.trim()}>
                ↑
              </button>
            </form>
          </div>
        </main>
      </div>
      )}
      
      {isSidebarOpen && (
        <div 
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.3)', zIndex: 10 }}
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
    </div>
  );
}

export default App;
