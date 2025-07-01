"""FastAPI backend for WordQuest Word Search Game.

Exposes the following APIs:
- User authentication (register/login)
- Puzzle generation & retrieval
- Result submission (completion time)
- Leaderboard & stats

This backend uses in-memory data. Replace data stores for production.

OpenAPI docs available at /docs
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from hashlib import sha256
from uuid import uuid4
from datetime import datetime

# App metadata & CORS
app = FastAPI(
    title="WordQuest Backend API",
    description=(
        "Backend for the WordQuest word search game. Handles authentication, "
        "puzzle serving, result submissions, and leaderboards."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "User registration and login"},
        {"name": "puzzle", "description": "Puzzle generation and fetch"},
        {"name": "game", "description": "Game result submissions"},
        {"name": "leaderboard", "description": "Leaderboard and stats"},
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory stores ---
USERS: Dict[str, Dict] = {}  # username => {password_hash, token}
TOKENS: Dict[str, str] = {}  # token => username
PUZZLES: Dict[str, Dict] = {}  # puzzle_id => puzzle_data
RESULTS: List[Dict] = []
TOPICS = ["animals", "sports", "fruits", "colors", "geography"]
DIFFICULTIES = ["easy", "medium", "hard"]


# --- Utility Functions ---
def hash_password(password: str) -> str:
    return sha256(password.encode("utf-8")).hexdigest()


def verify_token(token: str) -> Optional[str]:
    return TOKENS.get(token)


def create_access_token(username: str) -> str:
    token = str(uuid4())
    TOKENS[token] = username
    USERS[username]['token'] = token
    return token


def require_auth(token: str = Query(..., description="User authentication token")) -> str:
    """Get username from token or raise Auth error"""
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return username


# --- Schemas ---

class AuthRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=32, description="User's unique username"
    )
    password: str = Field(
        ..., min_length=4, max_length=64, description="User's password"
    )


class AuthResponse(BaseModel):
    token: str = Field(..., description="Access token for authenticated requests")
    username: str


class PuzzleRequest(BaseModel):
    topic: str = Field(
        ..., description=f"Word topic, one of: {', '.join(TOPICS)}"
    )
    difficulty: str = Field(
        ..., description=f"Difficulty level, one of: {', '.join(DIFFICULTIES)}"
    )


class PuzzleWord(BaseModel):
    word: str
    start_row: int
    start_col: int
    direction: str  # e.g., "horizontal", "vertical", "diagonal-up", "diagonal-down"


class PuzzleData(BaseModel):
    id: str
    created_at: datetime
    grid: List[List[str]] = Field(..., description="2D grid of single letters")
    words: List[PuzzleWord] = Field(..., description="Words hidden in grid")
    topic: str
    difficulty: str


class PuzzleListResponse(BaseModel):
    puzzles: List[PuzzleData]


class SubmitResultRequest(BaseModel):
    puzzle_id: str
    time_seconds: int = Field(
        ..., gt=0, description="Time taken in seconds to solve the puzzle"
    )


class LeaderboardEntry(BaseModel):
    username: str
    time_seconds: int
    puzzle_id: str
    completed_at: datetime


class LeaderboardResponse(BaseModel):
    entries: List[LeaderboardEntry]


# PUBLIC_INTERFACE
@app.get("/", tags=["root"])
def health_check():
    """Root health check."""
    return {"message": "Healthy"}


# --- Auth Endpoints ---

# PUBLIC_INTERFACE
@app.post(
    "/auth/register",
    response_model=AuthResponse,
    tags=["auth"],
    summary="Register user",
    description="Register a new user with username and password.",
)
def register(auth: AuthRequest):
    if auth.username in USERS:
        raise HTTPException(status_code=400, detail="Username already exists")
    USERS[auth.username] = {
        "password_hash": hash_password(auth.password),
        "token": None,
    }
    token = create_access_token(auth.username)
    return AuthResponse(token=token, username=auth.username)


# PUBLIC_INTERFACE
@app.post(
    "/auth/login",
    response_model=AuthResponse,
    tags=["auth"],
    summary="Login user",
    description="Login with username and password and receive an access token.",
)
def login(auth: AuthRequest):
    user = USERS.get(auth.username)
    if not user or user["password_hash"] != hash_password(auth.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(auth.username)
    return AuthResponse(token=token, username=auth.username)


# --- Puzzle Endpoints ---

def generate_word_list(topic: str, difficulty: str) -> List[str]:
    """Fake a word list based on topic/difficulty."""
    import random
    base = {
        "animals": [
            "cat", "dog", "elephant", "lion", "mouse", "tiger", "sheep", "horse"
        ],
        "sports": [
            "golf", "tennis", "soccer", "hockey", "cricket", "baseball"
        ],
        "fruits": [
            "apple", "pear", "grape", "cherry", "melon", "lemon"
        ],
        "colors": [
            "red", "green", "blue", "yellow", "violet", "orange"
        ],
        "geography": [
            "paris", "cairo", "nile", "amazon", "arctic", "andes"
        ],
    }
    words = base.get(topic, [])[:]
    size_map = {"easy": 5, "medium": 8, "hard": 12}
    count = size_map[difficulty]
    while len(words) < count:
        words.append(f"word{random.randint(1, 100)}")
    return words[:count]


def generate_grid(words: List[str], size: int) -> List[List[str]]:
    """Very simple word placement: just fill diagonally/horizontally for demo."""
    import random
    grid = [['' for _ in range(size)] for _ in range(size)]
    word_locs = []
    for idx, word in enumerate(words):
        placed = False
        # Try horizontal, then diagonal, then vertical
        for wdir in ['horizontal', 'diagonal-down', 'vertical']:
            if wdir == 'horizontal' and len(word) <= size:
                row, col = idx % size, 0
                if col + len(word) <= size and all(
                    grid[row][col + i] == '' for i in range(len(word))
                ):
                    for i, ch in enumerate(word):
                        grid[row][col + i] = ch
                    word_locs.append(
                        PuzzleWord(
                            word=word, start_row=row, start_col=col,
                            direction="horizontal"
                        )
                    )
                    placed = True
                    break
            if wdir == 'vertical' and len(word) <= size:
                row, col = 0, idx % size
                if row + len(word) <= size and all(
                    grid[row + i][col] == '' for i in range(len(word))
                ):
                    for i, ch in enumerate(word):
                        grid[row + i][col] = ch
                    word_locs.append(
                        PuzzleWord(
                            word=word, start_row=row, start_col=col,
                            direction="vertical"
                        )
                    )
                    placed = True
                    break
            if wdir == 'diagonal-down' and len(word) <= size:
                row = col = idx % (size - len(word) + 1)
                if all(grid[row + i][col + i] == '' for i in range(len(word))):
                    for i, ch in enumerate(word):
                        grid[row + i][col + i] = ch
                    word_locs.append(
                        PuzzleWord(
                            word=word, start_row=row, start_col=col,
                            direction="diagonal-down"
                        )
                    )
                    placed = True
                    break
        if not placed:
            # fallback: ignore the word if can't place
            continue
    # fill empty with random letters
    for i in range(size):
        for j in range(size):
            if grid[i][j] == '':
                grid[i][j] = chr(ord('a') + random.randint(0, 25))
    return grid, word_locs


# PUBLIC_INTERFACE
@app.post(
    "/puzzle/generate",
    response_model=PuzzleData,
    tags=["puzzle"],
    summary="Generate new puzzle",
    description="Generates a new word search puzzle with selected topic and difficulty.",
)
def generate_puzzle(payload: PuzzleRequest, username: str = Depends(require_auth)):
    # Basic size logic: easy=8x8, medium=12x12, hard=16x16
    size = {"easy": 8, "medium": 12, "hard": 16}[payload.difficulty]
    words = generate_word_list(payload.topic, payload.difficulty)
    grid, word_locs = generate_grid(words, size)
    puzzle_id = str(uuid4())
    now = datetime.utcnow()
    puzzle = {
        "id": puzzle_id,
        "created_at": now,
        "grid": grid,
        "words": [wl.model_dump() for wl in word_locs],
        "topic": payload.topic,
        "difficulty": payload.difficulty,
        "owner": username,
    }
    PUZZLES[puzzle_id] = puzzle
    return PuzzleData(
        id=puzzle_id,
        created_at=now,
        grid=grid,
        words=word_locs,
        topic=payload.topic,
        difficulty=payload.difficulty,
    )


# PUBLIC_INTERFACE
@app.get(
    "/puzzle/fetch",
    response_model=PuzzleData,
    tags=["puzzle"],
    summary="Fetch existing puzzle",
    description="Fetch a previously generated puzzle by its id.",
)
def fetch_puzzle(puzzle_id: str = Query(..., description="Puzzle id")):
    puzzle = PUZZLES.get(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    # convert words to PuzzleWord
    words = [
        PuzzleWord(**w) if not isinstance(w, PuzzleWord) else w
        for w in puzzle["words"]
    ]
    return PuzzleData(
        id=puzzle["id"],
        created_at=puzzle["created_at"],
        grid=puzzle["grid"],
        words=words,
        topic=puzzle["topic"],
        difficulty=puzzle["difficulty"],
    )


# --- Game Submission ---

# PUBLIC_INTERFACE
@app.post(
    "/game/submit-result",
    response_model=LeaderboardEntry,
    tags=["game"],
    summary="Submit puzzle completion result",
    description="Submit a puzzle completion time. Adds to leaderboard.",
)
def submit_result(data: SubmitResultRequest, username: str = Depends(require_auth)):
    if data.puzzle_id not in PUZZLES:
        raise HTTPException(status_code=400, detail="Invalid puzzle ID")
    result = {
        "username": username,
        "puzzle_id": data.puzzle_id,
        "time_seconds": data.time_seconds,
        "completed_at": datetime.utcnow(),
    }
    RESULTS.append(result)
    return LeaderboardEntry(**result)


# --- Leaderboard ---

# PUBLIC_INTERFACE
@app.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    tags=["leaderboard"],
    summary="Get global leaderboard",
    description="Returns leaderboard sorted by best completion time for all puzzles.",
)
def get_leaderboard(
    limit: int = Query(10, ge=1, le=100, description="Max entries to return")
):
    leaderboard = sorted(RESULTS, key=lambda r: r["time_seconds"])[:limit]
    entries = [LeaderboardEntry(**row) for row in leaderboard]
    return LeaderboardResponse(entries=entries)


# PUBLIC_INTERFACE
@app.get(
    "/leaderboard/puzzle/{puzzle_id}",
    response_model=LeaderboardResponse,
    tags=["leaderboard"],
    summary="Get leaderboard for puzzle",
    description="Returns leaderboard entries only for the specified puzzle.",
)
def get_puzzle_leaderboard(
    puzzle_id: str,
    limit: int = Query(10, ge=1, le=50, description="Max entries to return")
):
    entries = sorted(
        [r for r in RESULTS if r["puzzle_id"] == puzzle_id],
        key=lambda r: r["time_seconds"],
    )[:limit]
    return LeaderboardResponse(entries=[LeaderboardEntry(**row) for row in entries])


# --- Game Metadata ---

# PUBLIC_INTERFACE
@app.get(
    "/puzzle/topics",
    response_model=List[str],
    tags=["puzzle"],
    summary="Get puzzle topics",
    description="List all available puzzle topics.",
)
def get_topics():
    return TOPICS


# PUBLIC_INTERFACE
@app.get(
    "/puzzle/difficulties",
    response_model=List[str],
    tags=["puzzle"],
    summary="Get puzzle difficulties",
    description="List all supported difficulty levels.",
)
def get_difficulties():
    return DIFFICULTIES


# --- OpenAPI notes ---

@app.get(
    "/docs/ws",
    tags=["root"],
    summary="WebSocket API Usage",
    include_in_schema=False,
)
def ws_notes():
    """
    For real-time features (chat/game events) use WebSocket endpoint (not implemented in this template).
    """
    return {
        "info": (
            "No WebSocket endpoints are currently implemented. "
            "All functionality is REST-based."
        )
    }

# End of file.
