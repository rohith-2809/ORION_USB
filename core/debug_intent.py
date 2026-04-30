import re
def test_intent(text):
    print(f"\nScanning: '{text}'")
    t = text.lower().strip()

    # The regex from intent_classifier.py
    m_doc = re.search(
        r"\b(create|generate|write|make|draft)\b.+"
        r"\b(document|report|paper|article|guide|manual|presentation|ppt)\b",
        t
    )

    if m_doc:
        print("✅ Match Found!")
        print(f"Match object: {m_doc.group(0)}")

        # Topic extraction logic
        topic_match = re.search(r"\b(about|on|covering|titeld)\s+(.+?)(\s+in\s+\w+)?$", t)
        if topic_match:
            print(f"Topic Match Group 2: '{topic_match.group(2)}'")
        else:
            print("Topic fallback path...")
            post_doc = re.split(r"\b(document|report|paper|article|guide)\b", t)[-1]
            print(f"Post-doc content: '{post_doc}'")

    else:
        print("❌ No Match.")

# Test cases
test_intent("Create a document about Quantum Computing in docx")
test_intent("Generate report on AI Safety formatted as pdf")
test_intent("make a paper about something")
