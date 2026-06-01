FROM python:3.10

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Copy requirements and install
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy the rest of the application
COPY --chown=user . /app

# Hugging Face requires the app to listen on port 7860
ENV PORT=7860

# Command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "app_server:app"]
