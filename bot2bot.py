import requests

def send_prompt_to_lm_studio(prompt):
    url = "http://localhost:1111/v1/chat/completions"
    messages = [
        {"role": "user", "content": prompt}
    ]

    data = {
        "messages": messages,
        "max_tokens": 100,
        "temperature": -1.7
    }

    try:
        response = requests.post(url, json=data)

        if response.status_code == 200:
            result = response.json()
            generated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(generated_text)
        else:
            print(f"Error: HTTP {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    send_prompt_to_lm_studio("Tell me what this user said in this tweet https://x.com/ChShersh/status/2007848920786083922 .")
