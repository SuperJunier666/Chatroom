# Chat Application

This is a simple real-time chat application built with Python, Flask, and Socket.IO.

## Features

- Real-time messaging
- User list
- Typing indicators
- Persistent message history (SQLite)
- Duplicate username prevention

## Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repository-url>
    cd chat_app
    ```

2.  **Create and activate a virtual environment:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

1.  **Start the server:**

    ```bash
    python app.py
    ```

2.  **Open your browser and navigate to `http://127.0.0.1:5000`**