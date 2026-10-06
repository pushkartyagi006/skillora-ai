# Skillora AI

**AI Lab Project**
Under the mentorship of **Anjali Srivastava**

> AI-powered platform for resume analysis, project evaluation, interview preparation, and career assistance.

**Live demo:** https://skillora-ai-2828.onrender.com

> Hosted on Render's free plan. If nobody has visited for ~15 minutes, the first load can take 50 seconds or more while the server wakes up.

---
## Team

| Member | Role |
|--------|------|
| **Pushkar Tyagi** | Backend and AI Integration Lead |
| **Maksud Ansari** | Frontend and Evaluation Modules Lead |

## About the Project

Skillora AI is a web application powered by Google's Gemini AI that helps students, job seekers, teachers, and companies with career-related tasks. It can analyze and build resumes, evaluate projects and reports, screen candidates, and provide personalized interview preparation.

---

## Features

- **User sign-up and login**
- **Resume AI:** Analyze, improve, and build resumes according to user requirements and job descriptions.
- **Project AI:** Analyze projects and reports, provide scores and suggestions, and generate project-related interview questions.
- **Interview AI:** Conduct technical, HR, behavioral, and project-based mock interviews with feedback.
- **Teacher AI:** Evaluate multiple student reports against given criteria and provide approved/unapproved lists with reasons.
- **Hiring AI:** Screen multiple resumes according to company requirements and identify suitable candidates.

---

## Tech Stack

| Part | Technology |
|------|------------|
| Backend | Python 3, FastAPI |
| Server | Uvicorn |
| AI | Google Gemini API |
| Frontend | HTML, CSS, JavaScript |
| Hosting | Render (Free plan) |
| Version control | Git and GitHub |

---

## Project Structure

```
skillora-ai/
├── Backend/
│   ├── main.py            # FastAPI application entry point
│   ├── requirements.txt   # Python dependencies
│   └── .env               # Secret keys (not uploaded to GitHub)
├── [frontend files, e.g. login.html and feature pages]
└── README.md
```

---

## Run It Locally

1. **Clone the repository**
   ```bash
   git clone https://github.com/pushkartyagi006/skillora-ai.git
   cd skillora-ai/Backend
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Mac/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create a `.env` file inside `Backend/`**
   ```
   GEMINI_API_KEY=your_api_key_here
   GEMINI_MODEL=your_model_name_here
   ```
   Get a free key from [Google AI Studio](https://aistudio.google.com/).

5. **Start the server**
   ```bash
   uvicorn main:app --reload
   ```

6. Open `http://127.0.0.1:8000` in your browser.

---

## Environment Variables

| Name | Description |
|------|-------------|
| `GEMINI_API_KEY` | Your Google Gemini API key (required) |
| `GEMINI_MODEL` | Name of the Gemini model to use |

**Never upload your `.env` file or share your API key.** Add `.env` to `.gitignore`.

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Shows server status and whether `ai_configured` is `true` |

---

## Deployment (Render)

| Setting | Value |
|---------|-------|
| Language | Python 3 |
| Branch | `main` |
| Root Directory | `Backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Environment variables | `GEMINI_API_KEY`, `GEMINI_MODEL` |

Every push to `main` on GitHub redeploys the site automatically.

---

## How to Use

1. Open the live link.
2. Go to `/login.html` and create an account.
3. Log in and open any feature page.
4. Upload the required resume, report, project details, or other information.
5. Enter requirements where applicable and let Skillora AI analyze the information.
6. Review the AI-generated results, feedback, scores, and suggestions.

---


**Mentor:** Anjali Srivastava

### Work Distribution

**Pushkar Tyagi**
- Designed the backend with Python and FastAPI, and wrote the API endpoints
- Integrated the Google Gemini API and wrote the AI prompts
- Built the user sign-up and login system
- Developed **Resume AI** (analyze, improve, and build resumes)
- Developed **Hiring AI** (screen multiple resumes against company requirements)
- Developed the AI logic for **Interview AI** (question generation and feedback)
- Managed GitHub, deployment on Render, and environment configuration

**Maksud Ansari**
- Designed and built the frontend (HTML, CSS, JavaScript): login page, dashboard, and all feature pages
- Developed **Project AI** (project and report analysis, scoring, suggestions, project-based questions)
- Developed **Teacher AI** (evaluate multiple student reports with approved/unapproved lists and reasons)
- Built the **Interview AI** interface (mock interview screens and feedback display)
- Handled testing, bug fixing, and UI improvements
- Prepared project documentation and the presentation

**Shared work**
- Project planning and idea selection
- Testing the final deployed website
- Report writing and final demo

---

## Future Improvements

- AI Career Copilot for personalized career guidance
- Skill gap analysis and personalized career roadmap
- Adaptive mock interviews and project viva preparation
- Career progress tracking and skill-based recommendations
- Portfolio builder and multiple resume versions
- Voice-based interview preparation and advanced analytics

---

## License

This project is developed as an academic AI Lab Project.
