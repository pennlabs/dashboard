FROM pennlabs/django-base:latest

COPY requirements.txt /app/
RUN uv pip install --system -r requirements.txt

COPY . /app/

CMD ["gunicorn", "dashboard.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2"]
