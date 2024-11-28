import json
import random
import re
from typing import List, Dict
import logging as log

from utils import getSentiment


class Rule:
    decomposition: re.Pattern[str]

    def __init__(
        self, decomposition: str, reassembly: List[str], topic: str | None = None
    ):
        self.reassembly = reassembly
        self.decomposition = self.__string_to_regex(decomposition)
        self.topic = topic

    def __string_to_regex(self, string: str) -> re.Pattern[str]:
        string = re.sub(r"\s+", " ", string)
        string = re.sub(r"(\w+)", lambda m: f"({m.group(1)})", string)
        string = re.sub(
            r"(\[.+])",
            lambda m: f"({m.group(1)[1:-1].replace(" ", "|").replace(")", "").replace("(", "")})",
            string,
        )
        string = re.sub(r" ?\* ?", "(.*)", string)
        return re.compile(string)

    def __repr__(self):
        return f"Rule(decomposition={self.decomposition}, reassembly={self.reassembly})"


class Keyword:
    def __init__(self, key: str, rank: int, rules: List[Rule]):
        self.key = key
        self.rank = rank
        self.rules = rules

    def __repr__(self):
        return f"Keyword(key={self.key}, rank={self.rank}, rules={self.rules})"


class Eliza:
    history: List[tuple[str, str]]

    def __init__(
        self,
        *,
        greetings: List[str],
        goodbyes: List[str],
        default: List[str],
        reflections: Dict[str, str],
        pre: Dict[str, str],
        keywords: Dict[str, Keyword],
        sentimentModifiers: Dict[str, List[str]],
        selfModifiers: Dict[str, List[str]],
        topicPhrases: List[str],
    ):
        self.greetings = greetings
        self.goodbyes = goodbyes
        self.default = default
        self.reflections = reflections
        self.pre = pre
        self.keywords = keywords
        self.sentimentModifiers = sentimentModifiers
        self.selfModifiers = selfModifiers
        self.topicPhrases = topicPhrases
        self.history = []
        self.__max_history = 10

    def __prepare_input(self, user_input: str) -> str:
        user_input = user_input.lower().strip()
        user_input = re.sub(r"\s*[.,!;?]+\s*", " . ", user_input)
        for key, value in self.pre.items():
            user_input = user_input.replace(key, value)
        return user_input

    def __match_keyword(self, phrase: str, keyword: Keyword) -> Rule | None:
        log.debug("match_keyword: %s, %s", phrase, keyword.key)
        for rule in keyword.rules:
            log.debug("matching rule: %s", rule.decomposition)
            if rule.decomposition.match(phrase):
                log.debug("rule matched: %s", rule.decomposition)
                return rule
        return None

    def __get_matches(self, rule: Rule, phrase: str) -> List[str]:
        matches = rule.decomposition.findall(phrase)
        if isinstance(matches[0], tuple):
            matches = matches[0]
        return [m.strip() for m in matches]

    def __substitute(self, matches: List[str]) -> List[str]:
        result = " && ".join(matches)
        for key, value in self.reflections.items():
            result = re.sub(rf"\b{key}\b", value, result)
        return result.split(" && ")

    def __reassemble_phrase(self, rule: Rule, phrase: str) -> str:
        matches = self.__get_matches(rule, phrase)
        result = rule.reassembly[0]
        used = rule.reassembly.pop(0)
        log.debug(
            "reassemble_phrase: %s\nmatches: %s\nreassembly: %s",
            phrase,
            matches,
            result,
        )
        rule.reassembly.append(used)
        if result.startswith("="):
            log.debug("result.startswith('=')")
            new_rule = self.__match_keyword(phrase, self.keywords[result[1:]])
            if not new_rule:
                raise ValueError
            return self.__reassemble_phrase(new_rule, phrase)

        sentiment = getSentiment(phrase)
        topic = rule.topic if rule.topic else ""
        modifiers = self.selfModifiers if topic == ":me" else self.sentimentModifiers
        prefix = random.choice(modifiers.get(sentiment, [""]))
        for i, m in enumerate(self.__substitute(matches)):
            result = result.replace(f"${i+1}", m)
            prefix = prefix.replace(f"${i+1}", m)
            topic = topic.replace(f"${i+1}", m)
        if topic:
            self.history.append((topic, sentiment))
        if len(self.history) > self.__max_history:
            self.history.pop(0)
        log.debug(
            "sentiment: %s, prefix: %s, result: %s, topic: %s",
            sentiment,
            prefix,
            result,
            topic,
        )
        return prefix + " " + result if prefix else result

    def __respond_to_phrase(self, phrase: str) -> str | None:
        key_stack = []
        max_rank = -1
        words = phrase.split()
        log.debug("words: %s", words)
        for w in words:
            if w in self.keywords:
                key = self.keywords[w]
                log.debug("word: %s, rank: %d, max_rank: %d", w, key.rank, max_rank)
                key_stack.insert(0 if key.rank < max_rank else len(key_stack), w)
                max_rank = max(key.rank, max_rank)

        log.debug("key_stack: %s", key_stack)
        while key_stack:
            key = key_stack.pop()
            keyword = self.keywords[key]
            rule = self.__match_keyword(phrase, keyword)
            if rule:
                return self.__reassemble_phrase(rule, phrase)
        return None

    def __change_topic(self, user_input: str) -> str:
        sentiment = getSentiment(user_input)
        variants = sorted(self.history, key=lambda x: int(x[1]))

        topic = ""
        for t, s in variants:
            if s == sentiment:
                topic = t
                break
        if not topic:
            topic = random.choice(variants)[0]

        result = random.choice(self.topicPhrases)
        return result.replace("{topic}", topic.replace(":", ""))

    def respond(self, user_input: str) -> str | None:
        user_input = self.__prepare_input(user_input)
        if not user_input:
            return None

        phrases = [p.strip() for p in user_input.split(".")]
        log.debug("phrases: %s", phrases)
        result = ""

        for phrase in phrases:
            result = self.__respond_to_phrase(phrase)
            if result:
                return result

        if len(self.history) == 0:
            return random.choice(self.default)

        return self.__change_topic(user_input)

    def __repr__(self):
        return f"Eliza(greetings={self.greetings}, \
            goodbyes={self.goodbyes}, \
            default={self.default}, \
            reflections={self.reflections}, \
            keywords={self.keywords})"


def parse_json_file(file_path: str) -> Eliza:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    keywords = {}
    for keyword_data in data.get("keywords", []):
        rules = [Rule(**rule) for rule in keyword_data.get("rules", [])]
        keyword = Keyword(
            key=keyword_data["key"], rank=keyword_data["rank"], rules=rules
        )
        keywords[keyword.key] = keyword
    eliza = Eliza(
        greetings=data.get("greetings", []),
        goodbyes=data.get("goodbyes", []),
        default=data.get("default", []),
        reflections=data.get("reflections", {}),
        pre=data.get("pre", {}),
        keywords=keywords,
        sentimentModifiers=data.get("sentimentModifiers", {}),
        selfModifiers=data.get("selfModifiers", {}),
        topicPhrases=data.get("topicPhrases", []),
    )

    return eliza


def main():
    log.basicConfig(level=log.DEBUG)
    file_path = "script.json"
    eliza = parse_json_file(file_path)

    loop = True

    def handle_goodbye():
        nonlocal loop
        print(random.choice(eliza.goodbyes))
        loop = False

    print(random.choice(eliza.greetings))
    while loop:
        try:
            user_input = input("> ")
            if user_input.lower().strip() == "bye":
                handle_goodbye()
                return

            response = eliza.respond(user_input)
            if response:
                print(response)
            else:
                handle_goodbye()
        except KeyboardInterrupt:
            print(random.choice(eliza.goodbyes))
            break


if __name__ == "__main__":
    main()
