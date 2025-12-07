from openai import OpenAI
from struct_bio_reasoner.utils.inference_auth_token import get_access_token

# Get your access token
access_token = get_access_token()

client = OpenAI(
    api_key=access_token,
    base_url="https://inference-api.alcf.anl.gov/resource_server/metis/api/v1"
)

response = client.chat.completions.create(
    model="gpt-oss-120b-131072",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms."}]
)

print(response.choices[0].message.content)
