"""测试 MiniMax 思考模式的 JSON 提取"""
import httpx, json, re, sys
sys.path.insert(0, '.')

api_key = '***'
api_base = 'https://api.minimaxi.com/v1'
model = 'MiniMax-M2.7'

# 模拟一个真实请求，看看 MiniMax 返回什么格式
payload = {
    'model': model,
    'messages': [
        {'role': 'system', 'content': 'You are a helpful assistant. Reply ONLY with JSON.'},
        {'role': 'user', 'content': 'Output exactly 3 words in JSON format: {"candidates": [{"name": "test"}]}'}
    ],
    'temperature': 0.7,
    'max_tokens': 200
}

with httpx.Client(timeout=30.0) as client:
    resp = client.post(
        f'{api_base}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload
    )
    print('status:', resp.status_code)
    result = resp.json()
    content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
    print('raw content repr:', repr(content[:600]))
    print()

    # 测试新的 _extract_json
    stripped = re.sub(r'<THINK>.*?</THINK>', '', content, flags=re.DOTALL)
    stripped = re.sub(r'<think>.*?', '', stripped, flags=re.DOTALL)
    print('stripped repr:', repr(stripped[:400]))
    print()

    # 找到 candidates
    cand_idx = stripped.find('"candidates":')
    print('candidates idx:', cand_idx)

    if cand_idx != -1:
        # 往前找 {
        depth = 0
        start = -1
        for i in range(cand_idx, -1, -1):
            c = stripped[i]
            if c == '{':
                if depth == 0:
                    start = i
                    break
                depth -= 1
            elif c == '}':
                depth += 1

        print('start:', start)
        if start != -1:
            for end_pos in range(start + 5, len(stripped) + 1):
                try:
                    candidate = json.loads(stripped[start:end_pos])
                    if isinstance(candidate, dict) and "candidates" in candidate:
                        print('SUCCESS! parsed JSON:', candidate)
                        break
                except Exception:
                    continue
            else:
                print('FAILED to parse JSON')
    else:
        print('candidates not found in stripped text')