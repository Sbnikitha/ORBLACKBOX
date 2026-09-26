# Command center. Tray photos for Synthetic Live are drawn on startup.
# Point LLM_URL and VLM_URL at the Nano if those ports are up. Otherwise the local stand-in answers.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8501"]
