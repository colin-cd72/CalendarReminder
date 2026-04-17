def classify(event, config):
    for rule in config.get("silence_rules", []):
        match = rule.get("match", {})
        if "eventType" in match and event.get("eventType") == match["eventType"]:
            return ("silence", rule["name"])
    return ("keep", None)
