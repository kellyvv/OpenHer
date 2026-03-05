import asyncio
from openai import AsyncOpenAI

async def test():
    client = AsyncOpenAI(base_url='http://127.0.0.1:11434/v1', api_key='ollama')
    
    print("Test 1: Normal Generation")
    try:
        r1 = await client.chat.completions.create(
            model='qwen3.5:9b',
            messages=[{'role': 'user', 'content': 'Hello, are you there?'}]
        )
        print("R1:", repr(r1.choices[0].message.content))
    except Exception as e:
        print("R1 Error:", e)

    print("\nTest 2: Stream Mode")
    try:
        stream = await client.chat.completions.create(
            model='qwen3.5:9b',
            messages=[{'role': 'user', 'content': 'Say 1, 2, 3'}],
            stream=True
        )
        print("R2: ", end="")
        async for chunk in stream:
            c = chunk.choices[0].delta.content
            if c: print(c, end="")
        print()
    except Exception as e:
        print("R2 Error:", e)

    print("\nTest 3: JSON Format")
    try:
        r3 = await client.chat.completions.create(
            model='qwen3.5:9b',
            messages=[{'role': 'system', 'content': 'Output valid JSON.'}, {'role': 'user', 'content': 'Hi'}],
            response_format={'type': 'json_object'}
        )
        print("R3:", repr(r3.choices[0].message.content))
    except Exception as e:
        print("R3 Error:", e)

asyncio.run(test())
