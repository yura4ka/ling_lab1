from textblob import TextBlob


def getSentiment(text: str) -> str:
    sentiment = TextBlob(text).sentiment.polarity  # type: ignore
    if sentiment >= 0.75:
        return "2"
    if sentiment >= 0.25:
        return "1"
    if sentiment <= -0.75:
        return "-2"
    if sentiment <= -0.25:
        return "-1"
    return "0"
