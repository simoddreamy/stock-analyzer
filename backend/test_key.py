"""Check if API key is still valid"""
import httpx

settings_resp = httpx.get('http://127.0.0.1:18080/api/settings', timeout=10)
settings = settings_resp.json()
api_key = settings['api_key']
api_base = settings['api_base']

print(f"api_base: {api_base}")
print(f"api_key: {api_key[:10]}...")

# Test simple call
with httpx.Client(timeout=30.0) as client:
    resp = client.post(
        f'{api_base}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': settings['model'],
            'messages': [{'role': 'user', 'content': 'Say hello in 3 words'}],
            'max_tokens': 50
        }
    )
    print('status:', resp.status_code)
    if resp.status_code == 200:
        print('content:', resp.json()['choices'][0]['message']['content'][:200])
    else:
        print('error:', resp.text[:300])