# Medhavi Echelon Client

Next.js frontend for Medhavi Echelon authentication system.

## Getting Started

1. Install dependencies:
```bash
npm install
```

2. Create a `.env.local` file with:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Features

- Login page with email and password
- Signup page with email and password
- Form validation
- Error handling
- Redirect to dashboard after successful login
- Protected dashboard page
- Logout functionality

## Project Structure

```
client/
├── app/
│   ├── auth/
│   │   ├── login/page.tsx
│   │   └── signup/page.tsx
│   ├── dashboard/page.tsx
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── lib/
│   └── api.ts
├── package.json
├── tsconfig.json
├── next.config.js
└── tailwind.config.js
```

## API Integration

The frontend connects to the FastAPI backend running on `http://localhost:8000`. Make sure the backend server is running before using the frontend.

Available endpoints:
- POST `/auth/register` - Register new user
- POST `/auth/jwt/login` - Login user
- POST `/auth/jwt/logout` - Logout user
- GET `/users/me` - Get current user info

