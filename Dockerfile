# 1. सबसे लेटेस्ट और स्टेबल बेस इमेज का उपयोग
FROM python:3.11-slim-bookworm

# 2. वर्किंग डायरेक्टरी सेट करना
WORKDIR /app

# 3. पहले requirements.txt कॉपी करें (Docker Cache का फायदा लेने के लिए)
COPY requirements.txt .

# 4. बिल्ड टूल्स इंस्टॉल करें -> पैकेजेस इंस्टॉल करें -> बिल्ड टूल्स को वापस डिलीट करें (Single Layer Optimization)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    python3-dev \
    && pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. अब बाकी का पूरा कोड कॉपी करें
COPY . .

# 6. बॉट स्टार्ट करने की कमांड
CMD ["python3", "bot.py"]
