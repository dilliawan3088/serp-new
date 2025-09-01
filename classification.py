import openai
from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

# Get the OpenAI API key from the environment
openai.api_key = os.getenv('OPENAI_API_KEY')

def classify_content_with_openai(content, title, url):
    # Prepare the refined prompt for classification
    prompt = f"""
You are a content classifier. Classify the following content into one of these categories:

1. **Product Page**: A page focused on selling a product or service. It contains details like pricing, features, benefits, and a call to action (e.g., 'Buy Now', 'Learn More').
   - Example: "Buy the best AI writing tool today! Affordable pricing with 24/7 support."

2. **List Post**: A page containing a list of items, products, or tools, usually for comparison or recommendations.
   - Example: "Top 10 AI writing tools you should try in 2025."

3. **How-To Guide**: A page offering step-by-step instructions on how to complete a task or solve a problem. Often includes detailed explanations and examples.
   - Example: "How to write effective blog posts using AI in 5 simple steps."

4. **Video**: A page that contains or links to a video (often a tutorial or informational video).
   - Example: "Watch this video on how to create content with AI."

5. **Forum**: A page from an online forum or discussion board, where users share their opinions, experiences, or ask questions.
   - Example: "What are the best AI writing tools according to Reddit users?"

6. **Other**: If none of the above categories apply.

---

**Content Title**: {title}
**URL**: {url}
**Content**: {content}

Based on the content, select one of the above categories. If the content does not fit any of the categories, select "Other". Be sure to classify accurately based on the primary purpose of the page.
"""

    try:
        # Make the OpenAI API request for GPT-4O Mini
        response = openai.Completion.create(
            model="gpt-4o-mini",  # Specify GPT-4O Mini model
            prompt=prompt,
            temperature=0.2,
            max_tokens=50  # Using a limited token count for GPT-4O Mini
        )

        # Get the classification result
        classification = response.choices[0].text.strip()

        # Ensure the classification is one of the valid categories
        if classification not in ['Product Page', 'List Post', 'How-To Guide', 'Video', 'Forum', 'Other']:
            classification = 'Other'  # Fallback to 'Other' if the classification is invalid

        return classification

    except Exception as e:
        # Handle errors (API issues, timeout, etc.)
        print(f"Error during classification for {url}: {e}")
        return "Error"  # Return 'Error' if something goes wrong
