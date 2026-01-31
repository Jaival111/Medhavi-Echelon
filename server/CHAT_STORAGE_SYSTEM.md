# Chat Storage System - Database Integration

## Overview

The chat system now stores all conversations in the database with full message history. Each user can have multiple chats, and each chat contains ordered messages.

## Database Schema

### Models

#### Chat Model
- `id` (UUID): Primary key
- `user_id` (UUID): Foreign key to User
- `name` (String): Chat title/name
- `created_at` (DateTime): Creation timestamp
- `updated_at` (DateTime): Last update timestamp
- **Relationship**: `messages` - One-to-many with Message model

#### Message Model
- `id` (UUID): Primary key
- `chat_id` (UUID): Foreign key to Chat
- `role` (String): Message role ('user', 'assistant', 'system')
- `content` (Text): Message content
- `sequence` (Integer): Message order in the chat
- `created_at` (DateTime): Creation timestamp
- **Relationship**: `chat` - Many-to-one with Chat model

#### User Model (Updated)
- **New Relationship**: `chats` - One-to-many with Chat model

## API Endpoints

### 1. Create New Chat
**POST** `/chat/`

Creates a new chat and sends the first message. Automatically generates a chat name from the first user message.

**Request Body:**
```json
{
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chat-uuid",
  "user_id": "user-uuid",
  "name": "Hello, how are you?",
  "created_at": "2026-01-31T10:00:00",
  "updated_at": "2026-01-31T10:00:00",
  "messages": [
    {
      "id": "msg-uuid-1",
      "chat_id": "chat-uuid",
      "role": "user",
      "content": "Hello, how are you?",
      "sequence": 1,
      "created_at": "2026-01-31T10:00:00"
    },
    {
      "id": "msg-uuid-2",
      "chat_id": "chat-uuid",
      "role": "assistant",
      "content": "I'm doing well, thank you!",
      "sequence": 2,
      "created_at": "2026-01-31T10:00:01"
    }
  ]
}
```

**Authentication:** Required (Bearer token)

---

### 2. Continue Existing Chat
**POST** `/chat/{chat_id}`

Add a new message to an existing chat conversation.

**Path Parameters:**
- `chat_id` (UUID): The chat identifier

**Request Body:**
```json
{
  "messages": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Previous response"},
    {"role": "user", "content": "New message"}
  ],
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.7
}
```

**Response:** Same as Create New Chat

**Authentication:** Required

---

### 3. Get All User Chats
**GET** `/chat/chats?skip=0&limit=100`

Retrieve all chats for the authenticated user with message counts.

**Query Parameters:**
- `skip` (int, optional): Number of records to skip (default: 0)
- `limit` (int, optional): Maximum records to return (default: 100)

**Response:**
```json
{
  "chats": [
    {
      "id": "chat-uuid",
      "user_id": "user-uuid",
      "name": "Hello, how are you?",
      "created_at": "2026-01-31T10:00:00",
      "updated_at": "2026-01-31T10:30:00",
      "message_count": 10
    }
  ],
  "total": 5
}
```

**Authentication:** Required

---

### 4. Get Specific Chat
**GET** `/chat/chats/{chat_id}`

Retrieve a specific chat with all its messages.

**Path Parameters:**
- `chat_id` (UUID): The chat identifier

**Response:**
```json
{
  "id": "chat-uuid",
  "user_id": "user-uuid",
  "name": "Chat name",
  "created_at": "2026-01-31T10:00:00",
  "updated_at": "2026-01-31T10:30:00",
  "messages": [
    {
      "id": "msg-uuid",
      "chat_id": "chat-uuid",
      "role": "user",
      "content": "Message content",
      "sequence": 1,
      "created_at": "2026-01-31T10:00:00"
    }
  ]
}
```

**Authentication:** Required

---

### 5. Get Chat Messages
**GET** `/chat/chats/{chat_id}/messages`

Get all messages for a specific chat (alternative to getting full chat).

**Path Parameters:**
- `chat_id` (UUID): The chat identifier

**Response:**
```json
[
  {
    "id": "msg-uuid-1",
    "chat_id": "chat-uuid",
    "role": "user",
    "content": "Message 1",
    "sequence": 1,
    "created_at": "2026-01-31T10:00:00"
  },
  {
    "id": "msg-uuid-2",
    "chat_id": "chat-uuid",
    "role": "assistant",
    "content": "Response 1",
    "sequence": 2,
    "created_at": "2026-01-31T10:00:01"
  }
]
```

**Authentication:** Required

---

### 6. Update Chat
**PATCH** `/chat/chats/{chat_id}`

Update chat metadata (e.g., rename).

**Path Parameters:**
- `chat_id` (UUID): The chat identifier

**Request Body:**
```json
{
  "name": "New chat name"
}
```

**Response:** Full chat object with messages

**Authentication:** Required

---

### 7. Delete Chat
**DELETE** `/chat/chats/{chat_id}`

Delete a chat and all its messages.

**Path Parameters:**
- `chat_id` (UUID): The chat identifier

**Response:**
```json
{
  "message": "Chat deleted successfully"
}
```

**Authentication:** Required

---

### 8. Security Check (Unchanged)
**POST** `/chat/security-check`

Check a prompt for security risks without executing it.

**Request Body:**
```json
{
  "prompt": "Text to check"
}
```

---

### 9. List Models (Unchanged)
**GET** `/chat/models`

List available Groq models.

---

## Features

### 1. **Automatic Chat Creation**
- First message automatically creates a new chat
- Chat name is derived from the first user message (max 50 chars)

### 2. **Session-Based Intent Tracking**
- Each chat has a unique ID used for intent analysis
- Intent shifts are tracked per chat session

### 3. **Message Ordering**
- Messages are ordered by sequence number
- Ensures consistent message order even with concurrent operations

### 4. **User Isolation**
- All operations are user-scoped
- Users can only access their own chats

### 5. **Cascade Deletion**
- Deleting a chat automatically deletes all its messages
- Deleting a user automatically deletes all their chats

## Database Migration

Run the migration script to create the new tables:

```bash
cd server
python migrate_db.py
```

This will create:
- `chats` table
- `messages` table
- Add relationship to `user` table

## Usage Examples

### Frontend Flow

#### 1. Starting a New Conversation
```javascript
// User sends first message
const response = await fetch('/chat/', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    messages: [
      { role: 'user', content: 'Hello!' }
    ]
  })
});

const chat = await response.json();
const chatId = chat.id; // Store this for future messages
```

#### 2. Continuing a Conversation
```javascript
// User sends another message in the same chat
const response = await fetch(`/chat/${chatId}`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    messages: [
      ...previousMessages,
      { role: 'user', content: 'Tell me more' }
    ]
  })
});
```

#### 3. Loading Chat History
```javascript
// Get all user's chats
const chatsResponse = await fetch('/chat/chats', {
  headers: { 'Authorization': 'Bearer YOUR_TOKEN' }
});
const { chats, total } = await chatsResponse.json();

// Load specific chat with all messages
const chatResponse = await fetch(`/chat/chats/${chatId}`, {
  headers: { 'Authorization': 'Bearer YOUR_TOKEN' }
});
const fullChat = await chatResponse.json();
```

## Security Integration

All messages pass through the security pipeline before being stored:
- Layer 0: Intent analysis (tracks shifts across chat history)
- Layer 1: Heuristic analysis
- Layer 2: ML classification
- Layer 3: Canary token testing

If a message is rejected by security:
- For new chats: The chat is deleted
- For existing chats: The message is not stored

## Error Handling

### Common Errors

- **400 Bad Request**: Invalid chat_id format or security rejection
- **404 Not Found**: Chat doesn't exist or doesn't belong to user
- **500 Internal Server Error**: Database or API errors

## Performance Considerations

1. **Message Count**: Use `/chat/chats` endpoint for listing (includes counts without loading all messages)
2. **Pagination**: Use `skip` and `limit` parameters for large chat lists
3. **Lazy Loading**: Messages are only loaded when accessing specific chats

## Future Enhancements

- [ ] Message search functionality
- [ ] Chat archiving
- [ ] Export chat history
- [ ] Shared chats (multi-user)
- [ ] Message reactions/annotations
- [ ] Voice message support
- [ ] File attachments
