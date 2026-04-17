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

        if "has_extended_property_prefix" in match:
            prefix = match["has_extended_property_prefix"]
            private = (event.get("extendedProperties") or {}).get("private") or {}
            if any(k.startswith(prefix) for k in private.keys()):
                return ("silence", rule["name"])

    return ("keep", None)
