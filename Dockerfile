# 1. सबसे लाइटवेट और फास्ट बेस इमेज
FROM python:3.11-slim-bookworm

# 2. एनवायरनमेंट वैरिएबल्स (Koyeb लॉग्स और स्पीड के लिए जरूरी)
# PYTHONUNBUFFERED=1 : लॉग्स तुरंत दिखेंगे (Koyeb पर लैग नहीं होगा)
# PYTHONDONTWRITEBYTECODE=1 : .pyc फाइल्स नहीं बनेंगी (स्टोरेज बचाएगा)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 3. सिस्टम टूल्स + FFmpeg (वीडियो थंबनेल और इन्फो के लिए बहुत जरूरी)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 4. वर्किंग डायरेक्टरी
WORKDIR /app

# 5. कैशिंग का फायदा उठाने के लिए पहले requirements कॉपी करें
COPY requirements.txt .

# 6. फास्ट इंस्टॉलेशन (बिना कैश जमा किए)
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 7. बाकी कोड कॉपी करें
COPY . .

# 8. बॉट स्टार्ट कमांड
CMD ["python3", "bot.py"]

