# Sample Project PRD: Todo List API

## Project Overview
Build a RESTful API for a todo list application with user authentication and task management.

## Goals
- Provide CRUD operations for todos
- Support user authentication with JWT
- Enable task filtering and search
- Ensure data persistence with PostgreSQL

## Requirements

### 1. User Authentication
- User registration with email and password
- User login with JWT token generation
- Password hashing with bcrypt
- Token expiration and refresh mechanism

### 2. Todo Management
- Create new todos with title, description, due date
- List all todos for authenticated user
- Update todo status (pending, in_progress, completed)
- Delete todos
- Mark todos as favorite

### 3. Todo Filtering & Search
- Filter by status
- Filter by date range
- Search by title/description
- Sort by creation date, due date, priority

### 4. API Endpoints

#### Auth Endpoints
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/refresh` - Refresh expired token

#### Todo Endpoints
- `GET /api/todos` - List all todos (with filters)
- `POST /api/todos` - Create new todo
- `GET /api/todos/:id` - Get single todo
- `PUT /api/todos/:id` - Update todo
- `DELETE /api/todos/:id` - Delete todo

### 5. Data Models

#### User
- id (UUID)
- email (unique, validated)
- password_hash
- created_at
- updated_at

#### Todo
- id (UUID)
- user_id (foreign key)
- title (string, required)
- description (text, optional)
- status (enum: pending, in_progress, completed)
- priority (enum: low, medium, high)
- due_date (datetime, optional)
- is_favorite (boolean)
- created_at
- updated_at

## Technical Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT with python-jose
- **Validation**: Pydantic
- **Testing**: pytest with pytest-asyncio

## Acceptance Criteria

### Functional Requirements
- [ ] User can register with valid email and password
- [ ] User can login and receive JWT token
- [ ] Authenticated user can create todos
- [ ] User can only see/modify their own todos
- [ ] Todo CRUD operations work correctly
- [ ] Filtering and search return accurate results

### Non-Functional Requirements
- [ ] API response time < 200ms for most endpoints
- [ ] All endpoints have proper error handling
- [ ] Input validation prevents SQL injection
- [ ] Passwords are securely hashed (bcrypt)
- [ ] API documentation available (OpenAPI/Swagger)

### Quality Requirements
- [ ] Unit test coverage > 80%
- [ ] All integration tests pass
- [ ] Code follows PEP 8 style guide
- [ ] No security vulnerabilities (basic OWASP checks)
- [ ] Database migrations are versioned

## Out of Scope (Future Enhancements)
- Real-time notifications
- Todo sharing between users
- File attachments
- Mobile app integration
- Email reminders

## Success Metrics
- All unit tests pass
- All integration tests pass
- API can handle 100 concurrent requests
- Code review approved
- Documentation complete

## Timeline Estimate
This is a single-phase MVP project. All features should be implemented and tested in one phase.

## Notes for Agents

### Dev Agent
- Use async/await for all database operations
- Implement proper error handling and logging
- Follow the project structure in app/ directory
- Write clean, testable code

### QA Agent
- Write comprehensive unit tests
- Create integration tests for API endpoints
- Test authentication edge cases
- Verify input validation works correctly
- Check for SQL injection vulnerabilities

## Dependencies
- fastapi
- sqlalchemy[asyncio]
- psycopg2-binary
- python-jose[cryptography]
- passlib[bcrypt]
- pydantic
- pytest
- pytest-asyncio
- httpx (for testing)

## Environment Variables
```
DATABASE_URL=postgresql://user:pass@localhost:5432/todoapp
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30
```

## Deliverables
1. Working FastAPI application
2. Database models and migrations
3. API endpoints with documentation
4. Unit and integration tests
5. README with setup instructions
