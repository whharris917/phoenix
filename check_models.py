import google.generativeai as genai

# --- Function to load API key from a file ---
def load_api_key():
    try:
        key_path = os.path.join(os.path.dirname(__file__), 'private_data', 'Gemini_API_Key.txt')
        with open(key_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
        
genai.configure(api_key=API_KEY)

print("Available Gemini Models:")
for model in genai.list_models():
  # We are checking for 'generateContent' to find models that can be used for chat/text generation
  if 'generateContent' in model.supported_generation_methods:
    print(model.name)