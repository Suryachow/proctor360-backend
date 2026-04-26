FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN apt-get update \
	&& apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
	&& rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY app ./app

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
