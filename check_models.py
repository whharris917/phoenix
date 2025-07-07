import google.generativeai as genai

# Make sure to replace this with your key
API_KEY = 'AIzaSyALFegx2Gslr5a-xzx1sLWFOzB1EQ0xVZY' 
genai.configure(api_key=API_KEY)

print("Available Gemini Models:")
for model in genai.list_models():
  # We are checking for 'generateContent' to find models that can be used for chat/text generation
  if 'generateContent' in model.supported_generation_methods:
    print(model.name)