from agents import workflow
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
import warnings

# Ignore LangChain deprecation warnings for cleaner CLI output
warnings.filterwarnings("ignore")

def main():
    print("==========================================================")
    print(" AI Gym Automation Multi-Agent (Minimax M2 Cloud via Ollama) ")
    print("==========================================================")
    print("Let our virtual staff (Coach, Nutritionist, Manager) build your plan!")
    print("Type 'exit' or 'quit' to terminate.\n")
    
    while True:
        user_input = input("Enter your fitness goal (e.g., 'I want to lose 10lbs in 3 months'): ")
        
        if user_input.lower() in ['exit', 'quit']:
            print("Exiting...")
            break
            
        if not user_input.strip():
            continue
            
        print("\n[System] Let's get to work! Our virtual staff is analyzing...")
        
        # Compile locally for CLI
        memory = MemorySaver()
        agent_app = workflow.compile(checkpointer=memory)
        
        # Create an initial state with the human message
        initial_state = {"messages": [HumanMessage(content=user_input)]}
        config = {"configurable": {"thread_id": "cli-thread-1"}}
        
        try:
            current_node = ""
            
            # Using stream_mode="messages" allows token-by-token streaming
            # so the output streams smoothly into the console like a chatbot!
            for chunk, metadata in agent_app.stream(initial_state, config, stream_mode="messages"):
                node_name = metadata.get("langgraph_node")
                
                # Check if the node generating the response has changed and print a nice header
                if node_name and node_name != current_node:
                    print(f"\n\n🏋️‍♂️ --- {node_name.capitalize()} is typing ---")
                    current_node = node_name
                
                # Print token
                if getattr(chunk, "content", None) and not isinstance(chunk, HumanMessage):
                    print(chunk.content, end="", flush=True)
                    
            print("\n\n================ Workflow Completed ================\n")
            
        except Exception as e:
            print(f"\n[Error] {str(e)}")
            print("Ensure that you have langgraph version 0.1.0 or higher.")
            print("Ensure that Ollama is running and the model 'minimax-m2:cloud' is pulled.")
            print("(Hint: Run `ollama pull minimax-m2:cloud` and keep the ollama app running)")

if __name__ == "__main__":
    main()
