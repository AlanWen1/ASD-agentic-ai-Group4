# Student 3 showcase checklist

Suggested duration: 60-90 seconds inside the team's 10-minute video.

1. Open the unified home page on port `3000` and select **Income & Pay Schedule Manager**.
2. Show the Student 3 page on port `3003` and explain the four monthly summary cards.
3. Create an income source, edit it, and either delete it or mark it inactive.
4. Create a pay schedule and update it from `scheduled` to `received`.
5. Use **Generate dates** to create expected payments from a recurring source.
6. Change the dashboard month to demonstrate filtering.
7. Ask: `Which expected payments are still outstanding or late?`
8. Explain that Python calculates all numbers and Qwen only interprets the trusted context.
9. Briefly show the three Student 3 containers and successful `student-3.yml` workflow.
10. Include the educational/no-advice disclaimer in the recording.

Evidence to capture for the technical report:

- Unified UI navigation to Student 3.
- Income-source CRUD screenshot.
- Pay-schedule CRUD screenshot.
- AI chat request and grounded response.
- `docker compose ps` showing the three Student 3 services.
- Passing pytest output.
- Passing GitHub Actions workflow.
- Yongjian's commit and pull-request history.
