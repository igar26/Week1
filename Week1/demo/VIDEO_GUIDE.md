# Record a 2–3 minute demo

Start Streamlit, open localhost, and select reference date 2026-10-09. On macOS press Shift–Command–5, select the browser area and enable your microphone under Options. Record the steps below. Save as `demo.mp4` or upload to the course portal.

| Time | Screen action | Suggested narration |
| --- | --- | --- |
| 0:00–0:20 | Show app title and mode | “This project analyzes a fictional hockey season with schedule, team statistics and seat sales.” |
| 0:20–0:45 | Run home games under 70% sold | “The tool filters upcoming home games and calculates occupancy from total sold divided by capacity.” |
| 0:45–1:10 | Run revenue by tier | “Revenue is computed in SQL as price times seats sold. Structured output tells Streamlit to draw this chart.” |
| 1:10–1:30 | Run attendance scatter | “Tickets sold is an attendance proxy. Opponent win rates are synthetic; this chart does not establish causation.” |
| 1:30–1:50 | Run discount suggestion | “This rule suggests a discount for unsold seats at the weakest-selling game. It does not forecast demand.” |
| 1:50–2:20 | Codex mode: ask a question, expand Tool calls and JSON | “Codex selects decorated LangChain tools. The CLI uses my saved login, the agent loop runs on LangGraph, and Pydantic validates the final output.” |
| 2:20–2:40 | Open LangSmith trace if enabled | “This trace shows the Python workflow and analytics tools. Codex internal model events are outside this trace.” |
| 2:40–3:00 | Show files briefly | “The generator, analytics, tools, agent, schema and UI are separate so I can test and extend them.” |

If you have no working Codex CLI login, record the four offline examples and explicitly say: “This recording demonstrates deterministic Python analytics and rendering. The Codex agent is implemented but has not been demonstrated.” Do not describe offline function calls as AI tool selection. Only show LangSmith after capturing a real Codex query.

Before submitting, replay the recording: confirm readable charts, audible narration, no exposed keys, and permission for the instructor to access the video. Put the video location and validation details in `SUBMISSION.md`.
