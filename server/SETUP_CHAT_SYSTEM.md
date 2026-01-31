# Quick Setup Guide for Chat Storage System

## Step 1: Database Migration

Run the migration script to create the new database tables:

```bash
cd server
python migrate_db.py
```

This creates:
- `chats` table
- `messages` table  
- Updates `user` table relationships

## Step 2: Test the System

### Option A: Using the API directly

1. **Start the server:**
```bash
cd server
uvicorn app.main:app --reload
```

2. **Authenticate** (get your Bearer token)

3. **Create a new chat:**
```bash
curl -X POST http://localhost:8000/chat/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello, can you help me?"}
    ]
  }'
```

4. **Get all your chats:**
```bash
curl http://localhost:8000/chat/chats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

5. **Get specific chat with messages:**
```bash
curl http://localhost:8000/chat/chats/{CHAT_ID} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

6. **Continue a conversation:**
```bash
curl -X POST http://localhost:8000/chat/{CHAT_ID} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Previous message"},
      {"role": "assistant", "content": "Previous response"},
      {"role": "user", "content": "New question"}
    ]
  }'
```

### Option B: Using Python

```python
import asyncio
import httpx

async def test_chat_system():
    base_url = "http://localhost:8000"
    token = "YOUR_TOKEN"
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        # Create new chat
        response = await client.post(
            f"{base_url}/chat/",
            headers=headers,
            json={
                "messages": [
                    {"role": "user", "content": "Hello!"}
                ]
            }
        )
        chat = response.json()
        chat_id = chat["id"]
        print(f"Created chat: {chat_id}")
        
        # Get all chats
        response = await client.get(
            f"{base_url}/chat/chats",
            headers=headers
        )
        chats = response.json()
        print(f"Total chats: {chats['total']}")
        
        # Get specific chat
        response = await client.get(
            f"{base_url}/chat/chats/{chat_id}",
            headers=headers
        )
        full_chat = response.json()
        print(f"Messages in chat: {len(full_chat['messages'])}")

asyncio.run(test_chat_system())
```

## Step 3: Verify Database

Check that the tables were created:

```bash
# If using PostgreSQL
psql -d your_database -c "\dt"

# Should show: chats, messages, user tables
```

## Key Points

1. **Authentication Required**: All chat endpoints require a valid Bearer token
2. **User Isolation**: Users can only access their own chats
3. **Auto-naming**: First message becomes the chat name (truncated to 50 chars)
4. **Session Tracking**: Each chat has a unique ID used for security intent tracking
5. **Message Ordering**: Messages are automatically sequenced

## Troubleshooting

### Database Connection Issues
- Check your `DATABASE_URL` in `.env`
- Ensure database server is running
- Verify database exists and user has permissions

### Migration Errors
- Drop existing tables if schema changed: `DROP TABLE messages, chats CASCADE;`
- Re-run migration: `python migrate_db.py`

### Import Errors
- Ensure all dependencies are installed
- Check Python path includes the server directory

### Authentication Errors
- Verify your Bearer token is valid and not expired
- Check that the user exists in the database

## Next Steps

1. Integrate with your frontend
2. Add error handling for edge cases
3. Implement chat search functionality
4. Add pagination for large message lists
5. Consider adding WebSocket support for real-time updates

For detailed API documentation, see [CHAT_STORAGE_SYSTEM.md](CHAT_STORAGE_SYSTEM.md)
