FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/artifacts

ENV DATABASE_URL=sqlite:///./data/avrone.db
ENV MAX_AGENT_DEPTH=3
ENV ALLOW_AGENT_EXECUTION=false
ENV SOURCE_DEFAULT=avrone-duekrey
ENV LLM_BASE_URL=http://127.0.0.1:4000/v1
ENV PORT=9100

EXPOSE 9100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]
