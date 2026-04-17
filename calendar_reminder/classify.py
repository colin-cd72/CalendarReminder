def classify(event, config):
    for rule in config.get("silence_rules", []):
        match = rule.get("match", {})

        if "eventType" in match and event.get("eventType") == match["eventType"]:
            return ("silence", rule["name"])

        if "organizer_email_endswith" in match:
            suffix = match["organizer_email_endswith"]
            email = (event.get("organizer") or {}).get("email", "")
            if email.endswith(suffix):
                return ("silence", rule["name"])

    return ("keep", None)
