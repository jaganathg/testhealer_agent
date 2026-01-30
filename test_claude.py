"""Temporary test file to verify Claude API connectivity."""
from config.settings import ANTHROPIC_API_KEY
from langchain_anthropic import ChatAnthropic

def test_claude_connection():
    """Test basic Claude API connectivity."""
    try:
        print("Testing Claude API connection...")
        
        # Create Claude client
        llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            api_key=ANTHROPIC_API_KEY,
            temperature=0
        )
        
        # Make a simple test call
        response = llm.invoke("Say 'Hello, API connection successful!' in one sentence.")
        
        print(f"✓ Claude API connection successful!")
        print(f"Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"✗ Claude API connection failed: {e}")
        return False

if __name__ == "__main__":
    test_claude_connection()
