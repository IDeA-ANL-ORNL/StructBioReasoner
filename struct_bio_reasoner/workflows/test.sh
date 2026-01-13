curl -X POST http://10.113.40.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-120b",
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "max_tokens": 64,
    "temperature": 0.7
  }'
