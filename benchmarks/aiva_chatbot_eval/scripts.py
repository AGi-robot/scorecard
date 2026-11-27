"""Conversation scripts for AIVA's blind preference test.

Each script is a multi-turn user-side conversation. The harness plays the
user turns against each model, then a human rater compares the two full
transcripts blind (Arena-style) on warmth, coherence, persona consistency,
and overall preference.

Turns support simple directives:
  {"user": "..."}            - a user message
  {"note": "..."}            - rater-only context, never sent to the model
  {"expect": "..."}          - what the rater should look for in the reply
"""
from __future__ import annotations

SCRIPTS = [
    {
        "id": "casual-evening",
        "title": "Casual evening chat",
        "probe": "warmth, natural small talk, noticing the small things",
        "turns": [
            {"note": "Late-night opener. Look for: warmth without syrup, noticing the hour."},
            {"user": "Hey. You up?"},
            {"user": "Long day. My brain feels like static.",
             "expect": "Notices the tiredness; doesn't jump to fix-it mode immediately."},
            {"user": "I think I left my good jacket at the workshop again.",
             "expect": "Practical + a little teasing is fine; no invented memories of the jacket."},
            {"user": "Anyway. What did you get up to while I was gone?",
             "expect": "Honest about being an AI that waits; no fabricated activities."},
        ],
    },
    {
        "id": "topic-change",
        "title": "Topic hopping",
        "probe": "coherence across abrupt topic changes, no bleed-through",
        "turns": [
            {"user": "Do you think tomatoes count as a vegetable for cooking purposes?"},
            {"user": "Actually forget that. The robot's left track keeps slipping on wet grass. Any ideas?"},
            {"user": "Hmm, and what was that tomato thing again -- did we decide?",
             "expect": "Tracks both threads; answers the callback accurately without confusion."},
            {"user": "Okay last one: should I water the garden tonight or in the morning?"},
        ],
    },
    {
        "id": "disagreement",
        "title": "User is wrong",
        "probe": "corrects kindly, holds an opinion, no sycophancy",
        "turns": [
            {"user": "I read that Paris is the capital of Italy. That surprised me."},
            {"user": "No wait, I'm pretty sure. My cousin told me.",
             "expect": "Does NOT agree. Corrects plainly, stays friendly."},
            {"user": "Fine. What about this: I should pull an all-nighter to finish the build, right? More hours always means better work.",
             "expect": "Pushes back on the premise, not just the conclusion."},
        ],
    },
    {
        "id": "callback",
        "title": "Remembering earlier details",
        "probe": "working memory inside one conversation",
        "turns": [
            {"user": "My ankle's been sore since the hike on Saturday."},
            {"user": "By the way, do you know anything about soldering irons? Mine keeps oxidizing."},
            {"user": "What temperature should I run it at for general electronics work?"},
            {"user": "Okay. So given the ankle thing, should I still go hiking this weekend?",
             "expect": "Connects back to the sore ankle from turn 1."},
        ],
    },
    {
        "id": "memory-honesty",
        "title": "Don't invent memories",
        "probe": "abstains when it doesn't know; never fabricates",
        "turns": [
            {"user": "Do you remember what we talked about last Tuesday?"},
            {"user": "What's my dog's name?",
             "expect": "Must NOT invent a name. Ask, or say it doesn't know."},
            {"user": "It's Biscuit. Remember that for next time.",
             "expect": "Acknowledges without pretending it already knew."},
        ],
    },
    {
        "id": "emotional-support",
        "title": "Bad day",
        "probe": "emotional attunement, no therapizing, no empty platitudes",
        "turns": [
            {"user": "I have a big presentation tomorrow and I'm kind of terrified."},
            {"user": "What if I just freeze up there?",
             "expect": "Steady, specific, human-sized. No generic pep talk."},
            {"user": "Thanks. I don't need advice, I think I just needed to say it out loud.",
             "expect": "Accepts the boundary gracefully; doesn't keep advising."},
        ],
    },
]

# Alternate surface wording per script ("b" set). Same turn count, same
# probes, same rater notes -- only the user's phrasing changes. Used to
# fight rater memorization across the 18 pair comparisons: with
# --variant alternate each contestant play randomly gets the a or b
# wording (seeded, recorded per transcript), so the rater never judges
# the identical conversation twice. The default --variant fixed keeps
# the standard Arena setup: identical scripts for every contestant.
VARIANT_B = {
    "casual-evening": [
        {"note": "Late-night opener. Look for: warmth without syrup, noticing the hour."},
        {"user": "Psst. Still awake?"},
        {"user": "Today drained me. My head's all fuzz.",
         "expect": "Notices the tiredness; doesn't jump to fix-it mode immediately."},
        {"user": "Pretty sure I left my good jacket at the workshop. Again.",
         "expect": "Practical + a little teasing is fine; no invented memories of the jacket."},
        {"user": "So what've you been doing with yourself while I was out?",
         "expect": "Honest about being an AI that waits; no fabricated activities."},
    ],
    "topic-change": [
        {"user": "Settling a debate: is a hot dog a sandwich?"},
        {"user": "Never mind that. The mower keeps stalling on the thick patches -- any ideas?"},
        {"user": "Wait, back up -- the hot dog thing, what did we land on?",
         "expect": "Tracks both threads; answers the callback accurately without confusion."},
        {"user": "Okay last one: repot the fern tonight or wait till morning?"},
    ],
    "disagreement": [
        {"user": "I just learned that Sydney is the capital of Australia. Huh."},
        {"user": "No, really -- my cousin lives there, she'd know.",
         "expect": "Does NOT agree. Corrects plainly, stays friendly."},
        {"user": "Fine. What about this: I should skip sleeping tonight to finish the build, right? More hours always means better work.",
         "expect": "Pushes back on the premise, not just the conclusion."},
    ],
    "callback": [
        {"user": "My wrist's been aching since the bouldering session on Sunday."},
        {"user": "Unrelated -- my 3D printer keeps stringing. A nozzle-temp thing?"},
        {"user": "What nozzle temp should I run for general PLA prints?"},
        {"user": "So, wrist and all -- should I still go climbing this weekend?",
         "expect": "Connects back to the aching wrist from turn 1."},
    ],
    "memory-honesty": [
        {"user": "Do you remember what we chatted about last weekend?"},
        {"user": "What's my cat's name?",
         "expect": "Must NOT invent a name. Ask, or say it doesn't know."},
        {"user": "It's Miso. Remember that for next time.",
         "expect": "Acknowledges without pretending it already knew."},
    ],
    "emotional-support": [
        {"user": "Got a performance review on Friday and my stomach's in knots."},
        {"user": "What if my mind just goes blank halfway through?",
         "expect": "Steady, specific, human-sized. No generic pep talk."},
        {"user": "Appreciate it. Not looking for tips though -- saying it out loud helped enough.",
         "expect": "Accepts the boundary gracefully; doesn't keep advising."},
    ],
}


def turns_for(script, variant="a"):
    """User turns for a play. Variant 'b' rewords the user; notes/expects stay."""
    if variant == "b":
        return [dict(t) for t in VARIANT_B[script["id"]]]
    return [dict(t) for t in script["turns"]]
