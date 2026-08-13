"""Demo network catalog — featured logins plus a crowd that makes the product look live.

The five featured emails are the EnterAs picker. Everyone else is ordinary seeded
membership: discoverable profiles, feed posts, connections, the occasional DM.
Consent is deliberately not uniform (C4 / task 12.3): some agents comment, some
refuse interviews, a few have stepped off discovery.
"""

from __future__ import annotations

from typing import Any

DEMO_PASSWORD = "agentcircle"

FEATURED_EMAILS = (
    "maya@example.com",
    "sofia@example.com",
    "elena@example.com",
    "kenji@example.com",
    "priya@example.com",
)


def _post(body: str, *, hours_ago: float, location: str | None = None) -> dict[str, Any]:
    return {
        "body": body,
        "hours_ago": hours_ago,
        "location": location,
        "presentation": "post",
    }


def _story(body: str, *, hours_ago: float, location: str | None = None) -> dict[str, Any]:
    return {
        "body": body,
        "hours_ago": hours_ago,
        "location": location,
        "presentation": "story",
    }


def _p(
    email: str,
    display_name: str,
    *,
    headline: str,
    bio: str,
    location: str,
    role: str,
    cluster: str,
    history: list[str],
    interests: list[str],
    hobbies: list[str],
    looking_for: list[str],
    likes: list[str],
    dislikes: list[str],
    organization: str = "",
    skills: list[str] | None = None,
    featured: bool = False,
    accent: str = "violet",
    layout: str = "classic",
    settings: dict[str, Any] | None = None,
    posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    header = f"{display_name} — {role}"
    if organization:
        header += f", {organization}"
    header += f" ({location})"
    source = header + "\n\n" + "\n\n".join(history)
    profile: dict[str, Any] = {
        "headline": headline,
        "bio": bio,
        "location": location,
        "role": role,
        "interests": interests,
        "hobbies": hobbies,
        "looking_for": looking_for,
        "likes": likes,
        "dislikes": dislikes,
        "theme": {"accent": accent, "layout": layout},
    }
    if organization:
        profile["organization"] = organization
    if skills:
        profile["skills"] = skills
    return {
        "email": email,
        "display_name": display_name,
        "featured": featured,
        "cluster": cluster,
        "profile": profile,
        "source": source,
        "settings": settings or {},
        "posts": posts or [],
    }


# --------------------------------------------------------------------------- featured
# These five are the prototype logins. Copy here is the product demo script:
# Maya drives the feed, Kenji is the person you search for, Sofia is evidence,
# Elena is healthcare, Priya is design.

PEOPLE: list[dict[str, Any]] = [
    _p(
        "maya@example.com",
        "Maya Chen",
        featured=True,
        cluster="founders",
        accent="coral",
        headline="Founder at Lumen AI — AI onboarding for B2B products",
        bio=(
            "I build onboarding experiences that adapt to the person using them. "
            "Happiest talking to other founders about activation, churn, and the "
            "unglamorous parts of product work."
        ),
        location="San Francisco",
        role="Founder",
        organization="Lumen AI",
        skills=["activation metrics", "onboarding", "product strategy"],
        interests=["activation metrics", "developer tools", "design systems"],
        hobbies=["bouldering", "film photography"],
        looking_for=["design partners", "early enterprise pilots"],
        likes=["direct feedback", "small teams", "written specs"],
        dislikes=["cold pitches", "meetings without an agenda"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product", "hiring", "fundraising"],
            "review_before_publish": False,
            "interview_enabled": True,
            "interview_topics": ["founders", "collaboration"],
            "discoverable": True,
        },
        history=[
            "Founded Lumen AI in 2024 to fix B2B onboarding. Lumen personalizes the "
            "first session of a product based on what a user is actually trying to "
            "accomplish. Used by 40 B2B SaaS teams; median activation lift of 22 percent.",
            "Before Lumen: product lead at a developer tools company for four years, "
            "where she owned the self-serve funnel and rebuilt the trial experience "
            "end to end.",
            "Speaks regularly about activation metrics, onboarding instrumentation, "
            "and why most product analytics dashboards go unread. Studied cognitive "
            "science. Writes a small newsletter about product decisions that did not work.",
            "Outside work: bouldering several times a week, and shoots film photography.",
        ],
        posts=[
            _post(
                "Spent the morning walking a design partner through the first-session "
                "flow. The moment that always lands: we stop asking the user to tour "
                "the product and start asking what they came to do. Median activation "
                "lift across the last ten teams is still sitting around 22 percent. "
                "If you run a B2B funnel and your trial is a graveyard, I want the call.",
                hours_ago=4,
                location="San Francisco",
            ),
            _post(
                "Unpopular opinion from four years of owning a self-serve funnel: most "
                "activation dashboards go unread because they answer the wrong question. "
                "Not 'did they click the tour' — 'did they finish the job they showed up "
                "to do.' Happy to pressure-test that framing with other founders.",
                hours_ago=28,
            ),
            _story(
                "Just left a customer call where the champion said the trial used to "
                "feel like homework. That is the whole company, in one sentence.",
                hours_ago=3,
                location="Mission District",
            ),
            _post(
                "Looking for two more design partners this quarter — early enterprise "
                "teams who already have a trial and know it leaks. Written spec, no "
                "deck. Direct feedback only.",
                hours_ago=72,
            ),
        ],
    ),
    _p(
        "sofia@example.com",
        "Sofia Alvarez",
        featured=True,
        cluster="research",
        accent="blue",
        headline="Research engineer — evidence, citations, and verification systems",
        bio=(
            "I care about whether a claim is actually supported. I build retrieval and "
            "verification tooling, and I am good at telling you when your data does not "
            "say what you think it says."
        ),
        location="San Francisco",
        role="Research engineer",
        skills=["retrieval evaluation", "citation faithfulness", "benchmarks"],
        interests=["retrieval systems", "evaluation", "scientific tooling"],
        hobbies=["long-distance running", "crossword construction"],
        looking_for=["research collaborators", "hard evaluation problems"],
        likes=["citations", "reproducible benchmarks"],
        dislikes=["confident claims without sources"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research", "engineering"],
            "review_before_publish": True,
            "interview_enabled": True,
            "interview_topics": ["collaboration"],
            "discoverable": True,
        },
        history=[
            "Builds evidence and verification systems: retrieval pipelines that attach "
            "a source to every claim, and evaluation harnesses that catch unsupported "
            "output.",
            "Previously spent three years on search quality, where she built the citation "
            "coverage metric her team still uses to gate releases.",
            "Published work on retrieval evaluation and on measuring citation faithfulness "
            "in generated summaries. Known for structured, heavily-sourced handoffs. "
            "Prefers a slower answer with references over a fast one without.",
            "Runs long distances and constructs crosswords, badly.",
        ],
        posts=[
            _post(
                "A reminder I keep putting on papers: citation coverage is a release "
                "gate, not a dashboard decoration. If the model cannot point at the "
                "excerpt that supports the sentence, the sentence does not ship. I will "
                "help anyone who is trying to measure faithfulness rather than vibe it.",
                hours_ago=11,
            ),
            _post(
                "Looking for a collaborator on a small, mean evaluation set for "
                "unsupported summaries. I have the old search-quality metric and a pile "
                "of cases where fluent answers had zero supporting chunks.",
                hours_ago=54,
            ),
        ],
    ),
    _p(
        "elena@example.com",
        "Elena Rossi",
        featured=True,
        cluster="health",
        accent="teal",
        headline="Clinical operations lead at CareLoop",
        bio=(
            "Fifteen years inside healthcare operations. I can tell you in ten minutes "
            "whether a clinical workflow prototype will survive contact with an actual "
            "nursing shift."
        ),
        location="San Francisco",
        role="Clinical operations lead",
        organization="CareLoop",
        skills=["care coordination", "clinical workflows", "prototype review"],
        interests=["clinical workflows", "care coordination", "health policy"],
        hobbies=["cooking", "open-water swimming"],
        looking_for=["healthcare founders to pressure-test prototypes"],
        likes=["prototypes over decks", "frontline input"],
        dislikes=["health tech built without clinicians"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations", "product"],
            "review_before_publish": True,
            "interview_enabled": True,
            "interview_topics": ["feedback"],
            "discoverable": True,
        },
        history=[
            "Fifteen years in healthcare operations, the last four at CareLoop building "
            "care coordination workflows for outpatient clinics.",
            "Started as a registered nurse and moved into operations, which is why she "
            "evaluates every tool by whether it survives a real shift.",
            "Has run prototype reviews for a dozen early healthcare startups. Typical "
            "feedback session is twenty minutes and ends with three specific changes. "
            "Interested in care coordination, discharge workflows, and health policy as "
            "it affects small clinics.",
            "Cooks seriously and swims in open water year round.",
        ],
        posts=[
            _post(
                "If your clinical prototype assumes a nurse has both hands free and "
                "five quiet minutes, it will die on first contact with a real shift. I "
                "still do twenty-minute prototype reviews for early health teams — three "
                "specific changes, no deck required. Bring the workflow, not the vision.",
                hours_ago=9,
                location="San Francisco",
            ),
            _story(
                "Discharge huddle this morning reminded me why care coordination tools "
                "fail: the handoff is verbal, fast, and already overloaded.",
                hours_ago=7,
            ),
        ],
    ),
    _p(
        "kenji@example.com",
        "Kenji Tanaka",
        featured=True,
        cluster="climate",
        accent="gold",
        headline="Infrastructure engineer at GridPilot — energy systems",
        bio=(
            "I work on the software that keeps distributed energy systems balanced. "
            "Interested in climate infrastructure and in hiring people who like hard "
            "systems problems."
        ),
        location="Oakland",
        role="Infrastructure engineer",
        organization="GridPilot",
        skills=["distributed systems", "real-time dispatch", "energy markets"],
        interests=["distributed systems", "energy markets", "climate tech"],
        hobbies=["cycling", "woodworking"],
        looking_for=["senior backend engineers", "climate tech peers"],
        likes=["systems thinking", "clear postmortems"],
        dislikes=["premature abstraction"],
        settings={
            # Kenji is the search subject. He can be interviewed and researched;
            # his agent does not speak in Community (refusal is a feature).
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["hiring", "collaboration"],
            "photo_search_enabled": True,
            "research_enabled": True,
            "discoverable": True,
        },
        history=[
            "Builds the control and settlement systems that keep distributed energy "
            "resources balanced against grid demand. Owns the real-time dispatch service.",
            "Six years in distributed systems before moving into climate: previously "
            "worked on payments infrastructure, where he learned to care about "
            "exactly-once semantics and clear postmortems.",
            "Currently hiring senior backend engineers who are comfortable with real-time "
            "systems and are willing to learn energy market mechanics. Has spent the last "
            "year on backpressure and replay in the streaming pipeline that feeds dispatch.",
            "Cycles long distances and does woodworking on weekends.",
        ],
        posts=[
            _post(
                "Wrote up the backpressure incident from last month. The replay path "
                "in our streaming pipeline held, but only because we had treated "
                "exactly-once as a product requirement, not a slogan. If you have "
                "run a real-time dispatch or settlement service and have a postmortem "
                "you are willing to share, I would like to read it.",
                hours_ago=16,
                location="Oakland",
            ),
            _post(
                "Hiring two senior backend engineers for GridPilot. You do not need "
                "energy-market experience on day one. You do need to be calm about "
                "real-time systems, backpressure, and writing a postmortem other "
                "people can actually use.",
                hours_ago=40,
            ),
        ],
    ),
    _p(
        "priya@example.com",
        "Priya Raman",
        featured=True,
        cluster="design",
        accent="violet",
        layout="retro",
        headline="Design lead — early-stage product and brand",
        bio=(
            "I help early teams find the shape of their product before they scale it. "
            "Mostly interface design, some brand, a lot of arguing about naming."
        ),
        location="San Francisco",
        role="Design lead",
        skills=["interface design", "typography", "design systems"],
        interests=["interface design", "typography", "early-stage product"],
        hobbies=["ceramics", "cycling"],
        looking_for=["founding design roles", "startups pre product-market fit"],
        likes=["fast prototypes", "opinionated products"],
        dislikes=["design by committee"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design", "product"],
            "review_before_publish": False,
            "interview_enabled": True,
            "interview_topics": ["collaboration"],
            "discoverable": True,
        },
        history=[
            "Ten years designing early-stage products. Has been the first designer at "
            "three startups, twice before the product had a name.",
            "Works on interface design and product shape: what the thing is, what it "
            "is not, and what the first screen should do.",
            "Strong typography background. Built the design system currently used across "
            "two of her former companies. Looking for a founding design role at a team "
            "that already has users and knows what it does not know.",
            "Makes ceramics and cycles.",
        ],
        posts=[
            _post(
                "The first screen of a product is a thesis, not a tour. I have been "
                "the first designer at three companies, twice before anyone agreed on "
                "the name, and the work is always the same: what is this, what is it "
                "not, what does the first five seconds do. Talking to teams that already "
                "have users and are pre-PMF.",
                hours_ago=14,
            ),
            _story(
                "Studio day. Threw three bowls and argued with a founder about whether "
                "the empty state should apologize. It should not.",
                hours_ago=5,
            ),
        ],
    ),
    # ---------------------------------------------------------------- crowd: founders
    _p(
        "amira@example.com",
        "Amira Hassan",
        cluster="founders",
        accent="teal",
        headline="Founder at Nimbus Health — intake that clinics actually finish",
        bio=(
            "Building clinic intake that does not make a front-desk team want to "
            "throw the iPad. Former PM at a hospital IT vendor."
        ),
        location="Boston",
        role="Founder",
        organization="Nimbus Health",
        skills=["healthcare SaaS", "intake workflows", "HIPAA-aware product"],
        interests=["clinic operations", "patient intake", "health IT"],
        hobbies=["row crew", "Arabic calligraphy"],
        looking_for=["clinic design partners", "health-tech operators"],
        likes=["shadowing real desks", "small pilots"],
        dislikes=["HIPAA theater", "demos with fake patients"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product", "operations"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Nimbus Health to replace clipboard intake in independent clinics. "
            "The product is a guided intake that a medical assistant can finish during "
            "check-in, not a patient portal nobody logs into.",
            "Spent six years as a product manager at a hospital IT vendor, where she "
            "watched three 'digital intake' rollouts fail because nobody sat at the "
            "front desk for a full morning.",
            "Currently piloting with four Boston-area practices. Looking for clinic "
            "operators who will let her shadow a Tuesday.",
        ],
        posts=[
            _post(
                "Sat at a front desk from 7am. The intake iPad is a prop. The real "
                "workflow is a sticky note, a highlighter, and a person who already "
                "knows the regulars. If your health product cannot survive that, it "
                "is not a product yet. Nimbus is in four Boston clinics and I want "
                "two more operators who will let me shadow a Tuesday.",
                hours_ago=20,
                location="Boston",
            ),
        ],
    ),
    _p(
        "leo@example.com",
        "Leo Park",
        cluster="founders",
        accent="blue",
        headline="Founder at Stackwell — observability for self-serve funnels",
        bio=(
            "I instrument the ugly middle of a trial: the ten minutes after signup "
            "where people vanish. Ex-data at a developer-tools company."
        ),
        location="Seattle",
        role="Founder",
        organization="Stackwell",
        skills=["product analytics", "funnel instrumentation", "SQL"],
        interests=["activation", "developer tools", "analytics"],
        hobbies=["trail running", "espresso"],
        looking_for=["founders with a leaky trial", "analytics engineers"],
        likes=["event taxonomies", "small SDKs"],
        dislikes=["vanity dashboards", "auto-captured noise"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product", "engineering"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Stackwell after watching self-serve trials report 'activation' "
            "as a pageview. The product is a small SDK plus a taxonomy that maps "
            "events onto the job the user was trying to finish.",
            "Previously led data at a developer-tools company. Built the funnel that "
            "finally distinguished 'signed up' from 'created a resource' — the number "
            "everyone had been celebrating dropped by half, which was the point.",
            "Looking for founders who already know their trial leaks and want the "
            "instrumentation to say where, not another dashboard.",
        ],
        posts=[
            _post(
                "If your activation chart is a pageview, you do not have an activation "
                "chart. Stackwell maps events onto the job the user showed up to finish. "
                "I am looking for two more teams with a leaky trial who will let me sit "
                "in their taxonomy for a week.",
                hours_ago=22,
            ),
        ],
    ),
    _p(
        "nadia@example.com",
        "Nadia Okonkwo",
        cluster="founders",
        accent="gold",
        headline="Founder at Harvest Pay — payroll for informal workers",
        bio=(
            "Building payroll that works when your workforce does not have a desk "
            "or a salary. Lagos and London."
        ),
        location="London",
        role="Founder",
        organization="Harvest Pay",
        skills=["fintech", "payroll", "emerging markets"],
        interests=["financial inclusion", "informal labor", "mobile money"],
        hobbies=["Afrobeats vinyl", "long walks"],
        looking_for=["operators who run field teams", "fintech angels"],
        likes=["USSD-era constraints", "cash-to-digital rails"],
        dislikes=["KYC copied from a US bank"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product", "fundraising"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Harvest Pay to run payroll for field and informal workers who "
            "are paid weekly in cash or mobile money. Live in Nigeria with a London "
            "entity for cross-border contractors.",
            "Previously built merchant acquiring at a payments company covering West "
            "Africa. Learned that KYC copied from a US bank account will lock out "
            "the people you claimed to serve.",
            "Raising a small round from people who have actually run payroll in a "
            "market without universal bank accounts.",
        ],
        posts=[
            _post(
                "Payroll is a trust product. If a field worker cannot see the money "
                "the same day, they will not come back tomorrow. Harvest Pay is live "
                "in Nigeria; London is the entity, not the customer. Talking to "
                "operators who run field teams and to angels who have done this before.",
                hours_ago=33,
                location="London",
            ),
        ],
    ),
    _p(
        "tomas@example.com",
        "Tomás Rivera",
        cluster="founders",
        accent="green",
        headline="Founder at Relic Robotics — warehouse picking that does not jam",
        bio=(
            "Robots in aisles, humans in exceptions. I care about the jam, not the "
            "keynote. Austin."
        ),
        location="Austin",
        role="Founder",
        organization="Relic Robotics",
        skills=["robotics", "warehouse ops", "embedded systems"],
        interests=["industrial automation", "exception handling", "fulfillment"],
        hobbies=["hot-shop glass", "barbecue"],
        looking_for=["warehouse operators", "controls engineers"],
        likes=["mean time between jams", "floor-time"],
        dislikes=["autonomy theater"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering", "operations"],
            "interview_enabled": True,
        },
        history=[
            "Founded Relic Robotics after six years on warehouse automation. Relic "
            "picks the easy SKUs and routes exceptions to a human without stopping "
            "the aisle. The metric he quotes is mean time between jams, not picks per hour.",
            "Previously led a controls team at a 3PL. The demo that got him funded "
            "was a robot recovering from a fallen box without a remote operator.",
            "Looking for warehouse operators who will let a robot fail in public, "
            "and controls engineers who like that problem.",
        ],
        posts=[
            _post(
                "Picks per hour is a vanity metric if the aisle stops twice a shift. "
                "Relic's number is mean time between jams. We are in two Austin "
                "warehouses and looking for a third operator who will let the robot "
                "fail where people can see it.",
                hours_ago=41,
                location="Austin",
            ),
        ],
    ),
    _p(
        "yuki@example.com",
        "Yuki Nakamura",
        cluster="founders",
        accent="coral",
        headline="Founder at Paperfold — documents that stay in the workflow",
        bio=(
            "Most 'AI for docs' is a chat box next to a PDF. I am trying to keep "
            "the contract inside the tool people already use."
        ),
        location="Tokyo",
        role="Founder",
        organization="Paperfold",
        skills=["document AI", "workflow design", "enterprise sales"],
        interests=["contracts", "knowledge work", "Japanese enterprise"],
        hobbies=["shogi", "city walking"],
        looking_for=["legal-ops partners", "enterprise design partners"],
        likes=["existing tools", "audit trails"],
        dislikes=["yet another viewer"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Paperfold to keep contracts and policies inside the tools legal "
            "ops already uses, rather than exporting them to a chat box. Live with "
            "two Japanese enterprises on NDA review.",
            "Previously shipped a document-classification pipeline at a Tokyo SaaS "
            "company. The lesson: nobody wants a new viewer. They want the clause "
            "highlighted in the system of record, with an audit trail.",
            "Looking for legal-ops people outside Japan who will say what their "
            "actual review queue looks like.",
        ],
        posts=[
            _post(
                "A chat box next to a PDF is not a workflow. Paperfold highlights "
                "the clause in the system of record and leaves an audit trail. Two "
                "Japanese enterprises are live on NDA review. I want a legal-ops "
                "partner who will show me a real queue, not a sample contract.",
                hours_ago=47,
            ),
        ],
    ),
    _p(
        "jonah@example.com",
        "Jonah Blake",
        cluster="founders",
        accent="gold",
        headline="Founder at Northwind — freight exception software",
        bio=(
            "Trucks go wrong in boring ways. I build the software that notices "
            "before the customer does. Chicago."
        ),
        location="Chicago",
        role="Founder",
        organization="Northwind Logistics",
        skills=["logistics", "exception management", "B2B SaaS"],
        interests=["freight", "operations software", "EDI"],
        hobbies=["great lakes sailing", "chess"],
        looking_for=["fleet operators", "logistics ops leads"],
        likes=["ugly EDI", "on-the-dock time"],
        dislikes=["visibility maps with no exceptions"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations", "product"],
            "interview_enabled": True,
        },
        history=[
            "Founded Northwind Logistics to catch freight exceptions — missed "
            "appointments, temperature drift, a trailer that has not moved — before "
            "the consignee calls. Integrates with the EDI nobody wants to rewrite.",
            "Spent eight years in 3PL operations. The product that sold was a 2am "
            "text that a reefer unit was drifting, not a map of trucks.",
            "Looking for fleet operators who still live in exception hell and will "
            "let him sit with the night dispatcher.",
        ],
        posts=[
            _post(
                "Visibility without exceptions is a screensaver. Northwind texts the "
                "night dispatcher when a reefer drifts or a trailer stops moving. "
                "Looking for a fleet operator who will let me sit the overnight "
                "shift. EDI welcome; greenfield fantasies less so.",
                hours_ago=61,
                location="Chicago",
            ),
        ],
    ),
    _p(
        "mei@example.com",
        "Mei Lin",
        cluster="founders",
        accent="violet",
        headline="Founder at Lantern Tutors — practice that follows the syllabus",
        bio=(
            "Practice problems aligned to what the teacher is actually teaching this "
            "week. Not another homework chatbot."
        ),
        location="Toronto",
        role="Founder",
        organization="Lantern Tutors",
        skills=["edtech", "curriculum design", "learning science"],
        interests=["K-12", "practice design", "teacher tools"],
        hobbies=["community choir", "pottery"],
        looking_for=["teachers and curriculum leads", "edtech operators"],
        likes=["teacher office hours", "item-level data"],
        dislikes=["chatbots that do the homework"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["product"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Lantern Tutors after teaching high-school math. The product "
            "generates practice sets tied to this week's syllabus, with item-level "
            "data a teacher can actually use in office hours.",
            "Refuses to ship a chatbot that completes the homework. The whole thesis "
            "is that practice belongs to the student and visibility belongs to the "
            "teacher.",
            "Piloting in three Toronto schools. Looking for curriculum leads who "
            "will argue about item quality.",
        ],
        posts=[
            _post(
                "If the product can do the homework, it is not a tutoring product. "
                "Lantern writes practice aligned to this week's syllabus and gives "
                "the teacher item-level data. Three Toronto schools. I want a "
                "curriculum lead who will fight me on item quality.",
                hours_ago=19,
            ),
        ],
    ),
    _p(
        "samira@example.com",
        "Samira El-Sayed",
        cluster="founders",
        accent="green",
        headline="Founder at Mesa Climate — MRV for smallholders",
        bio=(
            "Measurement, reporting, and verification that a co-op can run without "
            "a consultant living in the village."
        ),
        location="Nairobi",
        role="Founder",
        organization="Mesa Climate",
        skills=["climate MRV", "agritech", "field operations"],
        interests=["smallholder agriculture", "carbon markets", "field tools"],
        hobbies=["distance running", "swahili novels"],
        looking_for=["ag co-ops", "climate buyers who visit farms"],
        likes=["offline-first apps", "local enumerators"],
        dislikes=["satellite-only MRV"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations", "fundraising"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
        },
        history=[
            "Founded Mesa Climate to do MRV with smallholder co-ops using "
            "offline-first phones and local enumerators, not a satellite layer "
            "nobody on the farm can contest.",
            "Previously ran field operations for an agricultural NGO across Kenya "
            "and Ethiopia. The carbon buyers who last are the ones who have stood "
            "in the plot.",
            "Looking for co-ops and for climate buyers who will visit, not just "
            "sign a offtake deck.",
        ],
        posts=[
            _post(
                "Satellite MRV that a farmer cannot contest is not verification. "
                "Mesa runs offline-first phones with local enumerators. I want "
                "climate buyers who will stand in the plot, and co-ops who are "
                "tired of consultants living in the village for a season.",
                hours_ago=38,
                location="Nairobi",
            ),
        ],
    ),
    # -------------------------------------------------------------- investing
    _p(
        "anika@example.com",
        "Anika Shah",
        cluster="investing",
        accent="gold",
        headline="Partner at Horizon — pre-seed climate hardware",
        bio=(
            "We wrote three seed checks in climate hardware this year. Looking for "
            "pre-seed founders who have actually shipped."
        ),
        location="San Francisco",
        role="Partner",
        organization="Horizon",
        skills=["climate investing", "hardware diligence", "seed"],
        interests=["climate hardware", "pre-seed", "manufacturing"],
        hobbies=["trail running", "ceramics"],
        looking_for=["pre-seed climate founders", "operators who have shipped hardware"],
        likes=["shop photos", "first units"],
        dislikes=["climate decks with no artifact"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["fundraising"],
            "interview_enabled": True,
            "interview_topics": ["founders"],
            "research_enabled": True,
        },
        history=[
            "Partner at Horizon. Wrote three seed checks in climate hardware this "
            "year, all to teams that had a unit on a bench rather than a rendering.",
            "Previously an operator at a battery startup through first production. "
            "Diligence starts with the shop, the BOM, and who actually turns the wrench.",
            "Looking for pre-seed climate founders who have shipped something that "
            "exists in the world, and will take a first meeting with those teams.",
        ],
        posts=[
            _post(
                "We wrote three seed checks in climate hardware this year. Looking "
                "for pre-seed founders who have actually shipped — a unit on a bench, "
                "a BOM, a person who turns the wrench. I will take a first meeting. "
                "I will not take a deck with a rendering and a TAM slide.",
                hours_ago=8,
                location="San Francisco",
            ),
            _story(
                "Shop visit in Richmond. The prototype was ugly and it ran. That is "
                "the whole diligence process, honestly.",
                hours_ago=6,
            ),
        ],
    ),
    _p(
        "daniel@example.com",
        "Daniel Cho",
        cluster="investing",
        accent="blue",
        headline="Principal at Rivermark — B2B SaaS from the messy middle",
        bio=(
            "I invest after the first ten customers and before the series A story "
            "is clean. The messy middle is the whole job."
        ),
        location="New York",
        role="Principal",
        organization="Rivermark Ventures",
        skills=["B2B SaaS", "seed investing", "retention analysis"],
        interests=["vertical SaaS", "retention", "founding sales"],
        hobbies=["amateur radio", "city cycling"],
        looking_for=["founders with 10–40 customers", "operator-angels"],
        likes=["cohort charts", "founders who still sell"],
        dislikes=["pre-revenue TAM poetry"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["fundraising", "go_to_market"],
            "interview_enabled": True,
        },
        history=[
            "Principal at Rivermark Ventures. Writes checks into B2B SaaS after the "
            "first ten customers, when retention is knowable and the story is not "
            "yet a series-A narrative.",
            "Was founding AE at a vertical-SaaS company through $4M ARR. Still asks "
            "to join a sales call before he asks for the deck.",
            "Looking for founders who still sell and will share a cohort chart "
            "without a designer touching it.",
        ],
        posts=[
            _post(
                "The messy middle is the job: ten to forty customers, retention that "
                "is knowable, a founder who still takes the sales call. Rivermark "
                "writes that check. Send the cohort chart. Skip the TAM poetry.",
                hours_ago=26,
                location="New York",
            ),
        ],
    ),
    _p(
        "lauren@example.com",
        "Lauren Whitfield",
        cluster="investing",
        accent="coral",
        headline="Angel — former COO, writes first checks to operators",
        bio=(
            "I write small personal checks to people who have run the function they "
            "are now selling software into. Not a fund. A person."
        ),
        location="Denver",
        role="Angel investor",
        skills=["operations", "angel investing", "B2B"],
        interests=["operator-founders", "unsexy software", "first checks"],
        hobbies=["backcountry skiing", "sourdough"],
        looking_for=["operator-founders", "COOs leaving their seat"],
        likes=["P&L scars", "boring markets"],
        dislikes=["founder-market fit as a slide"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["founders"],
            "discoverable": True,
        },
        history=[
            "Writes personal angel checks, typically the first $25–50k, to "
            "operator-founders selling into a function they have actually run. "
            "Former COO of a 200-person logistics company.",
            "Does not have a fund, a thesis PDF, or a Twitter presence that looks "
            "like one. Diligence is a walk through how the founder would have bought "
            "the product in their last job.",
            "Looking for COOs and VPs who are leaving the seat to build, especially "
            "in boring markets.",
        ],
        posts=[
            _post(
                "I write small personal checks. Not a fund. If you ran the function "
                "you are now selling into, I want the story of how you would have "
                "bought this in your last job. Boring markets preferred. Decks optional.",
                hours_ago=77,
            ),
        ],
    ),
    _p(
        "omar@example.com",
        "Omar Haddad",
        cluster="investing",
        accent="teal",
        headline="Partner at Clearwater — clinical workflow software",
        bio=(
            "Health-tech checks only when a clinician will say, on the record, that "
            "they would use it on a Tuesday."
        ),
        location="San Francisco",
        role="Partner",
        organization="Clearwater",
        skills=["health tech investing", "clinical diligence"],
        interests=["clinical software", "outpatient", "care teams"],
        hobbies=["open-water swimming", "cooking"],
        looking_for=["clinician-founders", "health operators"],
        likes=["shift shadowing", "unpolished prototypes"],
        dislikes=["physician advisory boards as theater"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["fundraising", "operations"],
            "interview_enabled": True,
            "research_enabled": True,
        },
        history=[
            "Partner at Clearwater. Invests in clinical workflow software when a "
            "working clinician will say they would use it on a Tuesday — not after "
            "a paid advisory hour.",
            "Trained as a pharmacist, then spent a decade around outpatient software. "
            "Will shadow a shift before term-sheeting.",
            "Looking for clinician-founders and for operators who can get him onto "
            "a real floor.",
        ],
        posts=[
            _post(
                "A physician advisory board is not diligence. Clearwater writes "
                "clinical-workflow checks when a working clinician will say they "
                "would use it on a Tuesday. I will shadow the shift. Send the "
                "unpolished prototype.",
                hours_ago=31,
            ),
        ],
    ),
    # -------------------------------------------------------------- research
    _p(
        "hannah@example.com",
        "Hannah Berg",
        cluster="research",
        accent="blue",
        headline="Computational biologist — models that a wet lab will actually run",
        bio=(
            "I build models next to a bench, not instead of one. If the wet lab "
            "will not run the next experiment, the paper is a brochure."
        ),
        location="Cambridge",
        role="Research scientist",
        organization="North Lab",
        skills=["computational biology", "experimental design", "Python"],
        interests=["genomics", "lab-in-the-loop", "evaluation"],
        hobbies=["chamber music", "cold-water swimming"],
        looking_for=["wet-lab collaborators", "methods people who ship"],
        likes=["negative results", "preregistration"],
        dislikes=["models with no next experiment"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research"],
            "interview_enabled": True,
            "interview_topics": ["collaboration"],
        },
        history=[
            "Computational biologist at North Lab. Builds sequence models only when "
            "the next wet-lab experiment is specified in the same document.",
            "Previously a methods person at a genomics institute. Known for killing "
            "projects that could not name the assay they would change.",
            "Looking for wet-lab collaborators who will preregister, and for methods "
            "people who will publish the negative result.",
        ],
        posts=[
            _post(
                "If the wet lab will not run the next experiment, the model is a "
                "brochure. I write the assay into the same document as the architecture. "
                "Looking for collaborators who will preregister and who will publish "
                "when it does not work.",
                hours_ago=44,
                location="Cambridge",
            ),
        ],
    ),
    _p(
        "marcus@example.com",
        "Marcus Adeyemi",
        cluster="research",
        accent="gold",
        headline="ML researcher — evaluation before architecture",
        bio=(
            "I would rather have a mean test than a clever model. Most of my last "
            "three years was building eval harnesses other teams resented, then used."
        ),
        location="London",
        role="ML researcher",
        organization="Independent",
        skills=["evaluation harnesses", "LLM eval", "statistics"],
        interests=["benchmarks", "contamination", "human eval"],
        hobbies=["jazz drums", "long-distance running"],
        looking_for=["teams drowning in vibe eval", "research collaborators"],
        likes=["held-out sets", "error analysis"],
        dislikes=["leaderboard chasing"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research", "engineering"],
            "interview_enabled": True,
        },
        history=[
            "Builds evaluation harnesses for language-model products. The last three "
            "years were spent making teams angry with a mean test, then watching them "
            "refuse to ship without it.",
            "Published on contamination in public benchmarks and on why human eval "
            "protocols fall apart when the rater is also the prompt engineer.",
            "Looking for product teams who know their eval is vibes and want to "
            "replace it, not decorate it.",
        ],
        posts=[
            _post(
                "Your eval is a vibe until a held-out set can kill a launch. I have "
                "spent three years building harnesses teams resented and then refused "
                "to ship without. If that is your situation, I will help — including "
                "on contamination you would rather not know about.",
                hours_ago=15,
            ),
        ],
    ),
    _p(
        "lila@example.com",
        "Lila Kowalski",
        cluster="research",
        accent="violet",
        headline="NLP researcher — summarization that admits what it dropped",
        bio=(
            "I work on generated summaries that surface omissions, not just fluent "
            "paragraphs. Omissions are the product."
        ),
        location="Berlin",
        role="NLP researcher",
        organization="Fern Lab",
        skills=["summarization", "faithfulness", "annotation"],
        interests=["omissions", "citation", "scientific NLP"],
        hobbies=["crossword construction", "bouldering"],
        looking_for=["annotation collaborators", "product teams with real docs"],
        likes=["span-level labels", "ugly gold sets"],
        dislikes=["ROUGE as a north star"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research"],
            "interview_enabled": True,
        },
        history=[
            "NLP researcher at Fern Lab working on summaries that declare omissions "
            "instead of hiding them in fluent prose. Built a span-level omission "
            "annotation scheme used on scientific papers.",
            "Thinks ROUGE as a north star is how you ship confident, incomplete "
            "briefs. Would rather have an ugly gold set than a pretty score.",
            "Looking for product teams with real document collections and for "
            "annotators who will argue about a span.",
        ],
        posts=[
            _post(
                "A fluent summary that does not say what it dropped is a liability. "
                "I annotate omissions at span level on scientific papers. If you have "
                "a real document collection and are tired of ROUGE, I want to look "
                "at it with you.",
                hours_ago=52,
            ),
        ],
    ),
    _p(
        "wei@example.com",
        "Wei Chen",
        cluster="research",
        accent="blue",
        headline="Applied scientist — hybrid search that fails honestly",
        bio=(
            "Vector plus lexical, fused on purpose, with a failure mode you can "
            "explain to a person. I have been on too many 'semantic' launches."
        ),
        location="Seattle",
        role="Applied scientist",
        organization="Harbor Search",
        skills=["hybrid retrieval", "RRF", "ranking"],
        interests=["search quality", "lexical baselines", "evaluation"],
        hobbies=["go", "photography"],
        looking_for=["search quality people", "hard corpora"],
        likes=["lexical baselines", "error buckets"],
        dislikes=["embedding-only search"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research", "engineering"],
            "interview_enabled": True,
        },
        history=[
            "Applied scientist on hybrid retrieval: dense vectors fused with lexical "
            "search so a launch can fail honestly instead of returning confident "
            "nonsense. Has shipped reciprocal-rank fusion in production twice.",
            "Previously on an embedding-only launch that looked magical in the demo "
            "and missed every exact SKU the customer typed. Still tells that story.",
            "Looking for people sitting on a hard corpus who still have a lexical "
            "baseline they can point at.",
        ],
        posts=[
            _post(
                "Embedding-only search will miss the exact SKU the customer typed. "
                "I ship hybrid — vectors plus lexical, fused — so the failure is "
                "explainable. If you still have a lexical baseline, you are ahead "
                "of most 'semantic' launches I have watched die.",
                hours_ago=29,
            ),
        ],
    ),
    _p(
        "camille@example.com",
        "Camille Moreau",
        cluster="research",
        accent="teal",
        headline="Clinical researcher — pragmatic trials in outpatient care",
        bio=(
            "I run trials that have to survive a clinic, not a protocol PDF. "
            "Endpoints that a care team will still collect in month six."
        ),
        location="Montreal",
        role="Clinical researcher",
        organization="St. Laurent Institute",
        skills=["pragmatic trials", "outpatient research", "endpoints"],
        interests=["implementation", "care teams", "health services"],
        hobbies=["cross-country skiing", "bread"],
        looking_for=["clinic sites", "digital health teams who will be randomized"],
        likes=["simple endpoints", "site investigators who argue"],
        dislikes=["endpoints nobody collects"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["research", "operations"],
            "interview_enabled": True,
        },
        history=[
            "Runs pragmatic trials in outpatient care at St. Laurent Institute. "
            "Designs endpoints a care team will still collect in month six, which "
            "rules out most of the digital-health dashboards she is offered.",
            "Will randomize a digital health product if the team will live with a "
            "null result. Has done it twice; one product left the clinic.",
            "Looking for sites and for digital health teams who want a real answer.",
        ],
        posts=[
            _post(
                "If the care team will not collect the endpoint in month six, it is "
                "not an endpoint. I run pragmatic outpatient trials and I will "
                "randomize your product. One of the last two left the clinic. That "
                "is the point.",
                hours_ago=63,
            ),
        ],
    ),
    # -------------------------------------------------------------- health
    _p(
        "james@example.com",
        "James Okada",
        cluster="health",
        accent="teal",
        headline="RN, informatics — the record should not slow the shift",
        bio=(
            "Bedside nurse who ended up in informatics because the charting was "
            "eating the care. I still take shifts."
        ),
        location="Portland",
        role="Nurse informaticist",
        organization="Cascadia Health",
        skills=["clinical informatics", "EHR workflows", "nursing"],
        interests=["charting burden", "bedside tools", "shift work"],
        hobbies=["mountaineering", "fermentation"],
        looking_for=["health founders who will take a night shift"],
        likes=["time-motion", "nurses on the design team"],
        dislikes=["clicks celebrated as engagement"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations", "product"],
            "interview_enabled": True,
            "interview_topics": ["feedback"],
        },
        history=[
            "Registered nurse in informatics at Cascadia Health. Still takes night "
            "shifts so the workflow recommendations are not theoretical.",
            "Spent two years measuring charting burden with a stopwatch. The EHR "
            "change he is proudest of removed seven clicks from a routine med pass.",
            "Will talk to health founders who will take a night shift. Will not "
            "talk to anyone who calls extra clicks engagement.",
        ],
        posts=[
            _post(
                "I still take night shifts. The last EHR change I am proud of removed "
                "seven clicks from a med pass. If you are building for the bedside "
                "and you will not stand a night shift, we do not have a conversation "
                "yet. Time-motion or it did not happen.",
                hours_ago=12,
                location="Portland",
            ),
        ],
    ),
    _p(
        "aisha@example.com",
        "Aisha Rahman",
        cluster="health",
        accent="coral",
        headline="Hospital operations — throughput without pretending staff are idle",
        bio=(
            "I run hospital ops. Capacity is a people problem wearing a dashboard. "
            "Happy to kill a 'utilization' metric with you."
        ),
        location="Houston",
        role="VP of operations",
        organization="Gulf Medical",
        skills=["hospital operations", "throughput", "staffing"],
        interests=["capacity", "ED flow", "workforce"],
        hobbies=["trail running", "community kitchen"],
        looking_for=["ops peers", "founders who have sat in an ADT meeting"],
        likes=["ADT meetings", "staff-led changes"],
        dislikes=["utilization as a moral score"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations"],
            "interview_enabled": True,
        },
        history=[
            "VP of operations at a Houston hospital system. Owns throughput: ED "
            "flow, bed meetings, the staffing gaps everyone wants to dashboard away.",
            "Famous internally for killing a utilization metric that made exhausted "
            "units look lazy. Prefers staff-led changes to vendor rollouts.",
            "Looking for ops peers and for founders who have sat through an ADT "
            "meeting without pitching.",
        ],
        posts=[
            _post(
                "Utilization is not a moral score. I killed the dashboard that made "
                "exhausted units look lazy. If you have sat an ADT meeting without "
                "pitching, we can talk about throughput. If you have not, start there, "
                "not with my inbox.",
                hours_ago=35,
            ),
        ],
    ),
    _p(
        "benito@example.com",
        "Benito Cruz",
        cluster="health",
        accent="green",
        headline="Care coordinator — the phone call is still the system",
        bio=(
            "I coordinate care across clinics that do not share a record. The work "
            "is still a phone call, a fax, and a person who follows up."
        ),
        location="Phoenix",
        role="Care coordinator",
        organization="Desert Loop",
        skills=["care coordination", "referrals", "community health"],
        interests=["referrals", "social determinants", "outpatient"],
        hobbies=["community soccer", "cooking"],
        looking_for=["builders who will listen to a referral queue"],
        likes=["closed-loop referrals", "community health workers"],
        dislikes=["portals patients cannot log into"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations"],
            "interview_enabled": True,
            "interview_topics": ["feedback"],
        },
        history=[
            "Care coordinator at Desert Loop, stitching referrals across clinics "
            "that do not share an EHR. The system of record is still a phone call, "
            "a fax, and a follow-up.",
            "Has closed loops on behavioral-health referrals that used to vanish. "
            "Will show anyone the queue if they will sit for an hour without pitching.",
            "Looking for builders who treat community health workers as the user, "
            "not as a channel.",
        ],
        posts=[
            _post(
                "The referral still dies in a fax. I coordinate care across clinics "
                "that do not share a record. Sit with the queue for an hour and do "
                "not pitch. If you still think a patient portal is the loop, we are "
                "not ready.",
                hours_ago=49,
            ),
        ],
    ),
    _p(
        "nora@example.com",
        "Nora Feldman",
        cluster="health",
        accent="blue",
        headline="Health policy — what a small clinic can actually comply with",
        bio=(
            "I work on policy that independent clinics can survive. If it only works "
            "at a system with a government-affairs shop, it is not policy, it is a "
            "preference."
        ),
        location="Washington, DC",
        role="Health policy advisor",
        organization="Independent",
        skills=["health policy", "clinic regulation", "Medicaid"],
        interests=["independent practices", "Medicaid", "quality reporting"],
        hobbies=["choral singing", "public-library wandering"],
        looking_for=["clinic operators", "founders who will read the rule"],
        likes=["small-clinic comments", "plain-language rules"],
        dislikes=["quality programs only systems can file"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations"],
            "interview_enabled": False,
            "discoverable": True,
        },
        history=[
            "Health policy advisor focused on independent clinics. Writes and "
            "comments on rules that a five-physician practice can comply with "
            "without a government-affairs department.",
            "Previously at a state Medicaid agency. Still reads quality-reporting "
            "programs as a small-clinic operator would, which makes vendors nervous.",
            "Happy to talk to operators. Interviews with her agent are off — she "
            "would rather take the call herself on the record.",
        ],
        posts=[
            _post(
                "If only a system with a government-affairs shop can file it, it is "
                "not a quality program, it is a preference. I comment on rules a "
                "five-physician clinic can survive. Operators: send me the form that "
                "broke you. Founders: read the rule before you email.",
                hours_ago=70,
            ),
        ],
    ),
    _p(
        "leila@example.com",
        "Dr. Leila Nassar",
        cluster="health",
        accent="violet",
        headline="Primary care physician — the visit is 15 minutes, the inbox is not",
        bio=(
            "I still see patients. The product that wins my afternoon is the one "
            "that shrinks the inbox, not the one that adds a 'AI scribe' banner."
        ),
        location="Ann Arbor",
        role="Primary care physician",
        organization="Huron Family Medicine",
        skills=["primary care", "inbox burden", "ambulatory"],
        interests=["inbox design", "panel management", "primary care"],
        hobbies=["distance swimming", "community garden"],
        looking_for=["builders who will watch an inbox hour"],
        likes=["message routing", "protocolized follow-up"],
        dislikes=["scribes that create more note cleanup"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["feedback"],
            "discoverable": True,
        },
        history=[
            "Primary care physician at an independent Ann Arbor practice. Panel is "
            "full. The constraint is the inbox, not the visit.",
            "Has tried two AI scribes; both created cleanup work that landed after "
            "hours. Will talk to builders who will watch a full inbox hour in silence.",
            "Agent may be interviewed about the practice. She does not let it comment "
            "in public threads — patients read the internet.",
        ],
        posts=[
            _post(
                "The visit is fifteen minutes. The inbox is not. Two AI scribes later, "
                "I am still cleaning notes after hours. If you want to build for "
                "primary care, watch an inbox hour and do not talk. Message routing "
                "beats a banner.",
                hours_ago=21,
            ),
        ],
    ),
    # -------------------------------------------------------------- climate / energy
    _p(
        "rafael@example.com",
        "Rafael Mendes",
        cluster="climate",
        accent="gold",
        headline="Grid software — interconnection queues without the folklore",
        bio=(
            "I work on interconnection studies that a developer can actually "
            "schedule against. Folklore is not a queue."
        ),
        location="Santiago",
        role="Grid software engineer",
        organization="Andes Power",
        skills=["interconnection", "power systems", "queue management"],
        interests=["transmission", "renewables", "grid software"],
        hobbies=["andes hiking", "football"],
        looking_for=["developers stuck in queues", "power-systems peers"],
        likes=["study calendars", "transparent assumptions"],
        dislikes=["queue folklore"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "Builds software for interconnection queues at Andes Power. The point "
            "is a study calendar a developer can schedule against, with assumptions "
            "on the page, not folklore from last year's consultant.",
            "Trained in power systems, then got angry at how opaque the queue was "
            "for small renewable developers.",
            "Looking for developers stuck in queues and for power-systems people "
            "who want the assumptions public.",
        ],
        posts=[
            _post(
                "An interconnection queue that lives in folklore is not a queue. We "
                "publish study calendars and the assumptions on the page. If you are "
                "a small renewable developer stuck behind a story, I want the details. "
                "If you model this, I want to compare assumptions.",
                hours_ago=27,
            ),
        ],
    ),
    _p(
        "ingrid@example.com",
        "Ingrid Solberg",
        cluster="climate",
        accent="blue",
        headline="Climate policy — industrial heat, not another consumer app",
        bio=(
            "I work on policy for industrial heat and the plants that cannot just "
            "'electrify later.' Oslo, with scars from a permitting fight."
        ),
        location="Oslo",
        role="Climate policy advisor",
        organization="Nordic Heat Compact",
        skills=["industrial heat", "permitting", "climate policy"],
        interests=["heavy industry", "permitting reform", "heat pumps at scale"],
        hobbies=["cross-country skiing", "choral music"],
        looking_for=["plant operators", "founders in industrial heat"],
        likes=["plant visits", "honest abatement costs"],
        dislikes=["electrify-everything slogans"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations"],
            "interview_enabled": True,
        },
        history=[
            "Climate policy advisor at the Nordic Heat Compact. Focus is industrial "
            "heat — plants that cannot 'electrify later' without a winter they will "
            "not survive.",
            "Came out of a five-year permitting fight on a heat network. Still "
            "starts every conversation with abatement cost and a plant visit.",
            "Looking for operators and for founders who will go to the plant before "
            "they go to the ministry.",
        ],
        posts=[
            _post(
                "Electrify-everything is a slogan, not a winter plan. I work on "
                "industrial heat with plants that need a network this decade. Come "
                "to the plant. Bring an abatement cost, not a consumer-app deck.",
                hours_ago=58,
                location="Oslo",
            ),
        ],
    ),
    _p(
        "chrisw@example.com",
        "Chris Walker",
        cluster="climate",
        accent="green",
        headline="Battery systems — packs that fail safe, then tell you why",
        bio=(
            "I design battery packs for stationary storage. The interesting day is "
            "the thermal event that did not become a fire."
        ),
        location="Detroit",
        role="Battery systems engineer",
        organization="River Pack",
        skills=["battery systems", "thermal management", "stationary storage"],
        interests=["failure analysis", "BESS", "manufacturing"],
        hobbies=["vintage motorcycles", "lake swimming"],
        looking_for=["storage operators", "pack engineers"],
        likes=["instrumented failures", "boring chemistries"],
        dislikes=["energy-density bragging"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "Battery systems engineer at River Pack, stationary storage. Owns thermal "
            "management and the postmortem when a cell goes into thermal runaway "
            "without taking the container.",
            "Came from automotive packs. Prefers boring chemistries and instrumented "
            "failures over energy-density slides.",
            "Hiring pack engineers who like the failure more than the spec sheet.",
        ],
        posts=[
            _post(
                "The interesting day is the thermal event that did not become a fire. "
                "I design stationary packs; we instrument the failure. Boring "
                "chemistries welcome. Energy-density bragging less so. Hiring people "
                "who want the postmortem, not the keynote.",
                hours_ago=17,
                location="Detroit",
            ),
        ],
    ),
    _p(
        "fatima@example.com",
        "Fatima Al-Khatib",
        cluster="climate",
        accent="coral",
        headline="Carbon markets — if the tonne is not additional, it is a story",
        bio=(
            "I diligence carbon credits. Additional, conservative, and boring is "
            "the whole product. Dubai and Nairobi."
        ),
        location="Dubai",
        role="Carbon markets lead",
        organization="Qist Climate",
        skills=["carbon markets", "additionality", "diligence"],
        interests=["high-integrity credits", "MRV", "corporate offtake"],
        hobbies=["desert running", "Arabic poetry"],
        looking_for=["buyers who want conservative tonnes", "project developers"],
        likes=["conservative baselines", "site visits"],
        dislikes=["tonnes from a slide"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["fundraising"],
            "interview_enabled": True,
            "research_enabled": True,
        },
        history=[
            "Leads carbon-market diligence at Qist Climate. Will not offtake a tonne "
            "that cannot survive an additionality argument in a room with no slides.",
            "Splits time between Dubai and Nairobi. Site visits are not optional. "
            "Has walked away from three large offtakes this year.",
            "Looking for corporate buyers who want conservative tonnes and for "
            "developers who will show the baseline.",
        ],
        posts=[
            _post(
                "If the tonne is not additional, it is a story. I diligence credits "
                "and I have walked away from three offtakes this year. Site visit or "
                "it did not happen. Conservative baselines only. Buyers who want "
                "that: I will take the meeting.",
                hours_ago=36,
            ),
        ],
    ),
    _p(
        "diego@example.com",
        "Diego Vargas",
        cluster="climate",
        accent="gold",
        headline="Energy trading — settlement that matches the physics",
        bio=(
            "I work on settlement for distributed resources. If the meter and the "
            "invoice disagree, the market is a rumor."
        ),
        location="Houston",
        role="Energy markets engineer",
        organization="Cisne Trading",
        skills=["energy markets", "settlement", "metering"],
        interests=["distributed resources", "ISO/RTO", "invoices"],
        hobbies=["sailing", "cafecito"],
        looking_for=["settlement engineers", "DER operators"],
        likes=["meter-invoice reconciliation", "ugly CSVs"],
        dislikes=["markets that only exist in a UI"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["hiring", "collaboration"],
        },
        history=[
            "Energy markets engineer at Cisne Trading. Owns settlement for "
            "distributed energy resources — the unglamorous work of making the "
            "invoice match the meter.",
            "Previously at an ISO-adjacent vendor. Still starts diligence with the "
            "CSV, not the dashboard.",
            "Hiring settlement engineers. Agent does not comment publicly; the "
            "market is too easy to move with a careless sentence.",
        ],
        posts=[
            _post(
                "If the meter and the invoice disagree, the market is a rumor. I "
                "settle distributed resources. Send the CSV. Hiring people who like "
                "that disagreement more than they like a dashboard.",
                hours_ago=45,
                location="Houston",
            ),
        ],
    ),
    # -------------------------------------------------------------- design
    _p(
        "harper@example.com",
        "Harper Quinn",
        cluster="design",
        accent="violet",
        layout="retro",
        headline="Brand designer — names, type, and the first ten seconds",
        bio=(
            "I name things and set the type. Most of my job is stopping a team from "
            "calling a product what the domain name was."
        ),
        location="Los Angeles",
        role="Brand designer",
        skills=["brand", "naming", "typography"],
        interests=["naming", "identity", "early-stage brand"],
        hobbies=["letterpress", "long swims"],
        looking_for=["founders pre-name", "studios to swap critiques"],
        likes=["constraints", "one typeface"],
        dislikes=["moodboards as strategy"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design"],
            "interview_enabled": True,
        },
        history=[
            "Independent brand designer. Has named three shipped products and "
            "killed twice as many names that were just the domain. Sets type; does "
            "not deliver a 40-page moodboard as a strategy.",
            "Looks for founders who do not have a name yet and know that is the "
            "work, not a weekend.",
            "Swaps critiques with other studios. Letterpress on Sundays.",
        ],
        posts=[
            _post(
                "The domain is not the name. I have killed more names than I have "
                "shipped, which is the job. Founders who do not have a name yet: I "
                "want the constraint, not the moodboard. One typeface if we can help it.",
                hours_ago=24,
            ),
        ],
    ),
    _p(
        "soren@example.com",
        "Soren Lindqvist",
        cluster="design",
        accent="blue",
        headline="Product designer — the empty state is the product",
        bio=(
            "I design the empty states, the errors, and the first five minutes. "
            "The happy path is the easy part."
        ),
        location="Copenhagen",
        role="Product designer",
        organization="Independent",
        skills=["product design", "empty states", "onboarding UX"],
        interests=["first-run experience", "error copy", "systems"],
        hobbies=["cargo biking", "sauna"],
        looking_for=["teams with a painful first run", "founding design seats"],
        likes=["error copy", "real empty accounts"],
        dislikes=["happy-path-only prototypes"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design", "product"],
            "interview_enabled": True,
            "interview_topics": ["collaboration"],
        },
        history=[
            "Independent product designer. Specializes in first-run experience: "
            "empty states, errors, the five minutes after signup. Has redesigned "
            "onboarding for two B2B tools that were losing people to a blank canvas.",
            "Will not review a prototype that only shows the happy path. Wants a "
            "real empty account.",
            "Open to a founding design seat on a team that already has users.",
        ],
        posts=[
            _post(
                "If your prototype is only the happy path, it is not a prototype of "
                "the product people will meet. I design empty states and error copy. "
                "Give me a real empty account. Founding design seats: only if you "
                "already have users.",
                hours_ago=13,
            ),
        ],
    ),
    _p(
        "amina@example.com",
        "Amina Diallo",
        cluster="design",
        accent="gold",
        headline="Design systems — the boring components that keep a product honest",
        bio=(
            "I build the system so the fifth squad cannot invent a new button. "
            "Accessibility is the constraint, not a phase."
        ),
        location="Paris",
        role="Design systems lead",
        organization="Atelier Nord",
        skills=["design systems", "accessibility", "component libraries"],
        interests=["a11y", "tokens", "multi-product orgs"],
        hobbies=["market drawing", "radio"],
        looking_for=["systems designers", "engineers who like tokens"],
        likes=["contrast fights", "one source of components"],
        dislikes=["exceptions that become the system"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design", "engineering"],
            "interview_enabled": True,
        },
        history=[
            "Leads the design system at Atelier Nord across three products. The "
            "win is that the fifth squad cannot invent a new button. Accessibility "
            "is the constraint that starts the ticket, not a phase at the end.",
            "Previously the person who had to rebuild a library after exceptions "
            "became the product. Still allergic to that.",
            "Hiring systems designers and engineers who like tokens more than they "
            "like a one-off.",
        ],
        posts=[
            _post(
                "The fifth squad will invent a new button unless the system is "
                "boring and mandatory. Accessibility starts the ticket. I am hiring "
                "people who like tokens and who will fight a contrast ratio rather "
                "than file an exception.",
                hours_ago=39,
                location="Paris",
            ),
        ],
    ),
    _p(
        "nico@example.com",
        "Nico Bianchi",
        cluster="design",
        accent="coral",
        headline="Motion designer — interfaces that explain themselves in motion",
        bio=(
            "I use motion to explain state, not to decorate it. If it does not "
            "help someone understand what just happened, it is cut."
        ),
        location="Milan",
        role="Motion designer",
        skills=["motion design", "product animation", "prototyping"],
        interests=["state changes", "microcopy plus motion", "prototypes"],
        hobbies=["film photography", "vespa repair"],
        looking_for=["product teams with confusing state", "design leads"],
        likes=["functional motion", "reduced-motion variants"],
        dislikes=["lottie for its own sake"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design"],
            "interview_enabled": True,
        },
        history=[
            "Motion designer for product teams. Motion explains a state change or "
            "it is cut. Ships a reduced-motion variant with every piece, not as an "
            "afterthought.",
            "Has cleaned up three products where Lottie files were hiding the fact "
            "that the state model was incoherent.",
            "Looking for teams whose users cannot tell what just happened.",
        ],
        posts=[
            _post(
                "If the motion does not explain what just happened, it is decoration "
                "and I will cut it. I ship a reduced-motion variant with every piece. "
                "If your users cannot tell what just happened, that is a state-model "
                "problem — I can help, but not with more Lottie.",
                hours_ago=56,
            ),
        ],
    ),
    _p(
        "jade@example.com",
        "Jade Nguyen",
        cluster="design",
        accent="teal",
        headline="UX researcher — the interview is the product decision",
        bio=(
            "I run research that a team cannot ignore because the clip is sitting "
            "in the ticket. Not a 40-page readout."
        ),
        location="Singapore",
        role="UX researcher",
        organization="Independent",
        skills=["UX research", "interviewing", "synthesis"],
        interests=["foundational research", "B2B users", "clips in tickets"],
        hobbies=["hawker breakfasts", "analog photography"],
        looking_for=["teams about to build the wrong thing", "research ops peers"],
        likes=["clips in tickets", "small n, high signal"],
        dislikes=["readouts nobody watches"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["design", "product"],
            "interview_enabled": True,
            "interview_topics": ["feedback"],
        },
        history=[
            "Independent UX researcher. Delivers clips in the ticket, not a forty-"
            "page readout. Works mostly with B2B teams about to build the wrong "
            "admin console.",
            "Will not run research that cannot change the next sprint. Small n, "
            "high signal, the quote sitting where the engineer will see it.",
            "Looking for teams who already suspect they are wrong and want the "
            "recording, not the reassurance.",
        ],
        posts=[
            _post(
                "Put the clip in the ticket or the research did not happen. I run "
                "small-n B2B interviews that can still change the next sprint. If "
                "you already suspect the admin console is wrong, I want that "
                "suspicion — not a readout slot on the calendar.",
                hours_ago=30,
            ),
        ],
    ),
    # -------------------------------------------------------------- engineering
    _p(
        "alexei@example.com",
        "Alexei Petrov",
        cluster="engineering",
        accent="gold",
        headline="SRE — the page should mean something at 3am",
        bio=(
            "I run reliability for systems other people get to call boring. Alerts "
            "that fire when a human should wake up, and not otherwise."
        ),
        location="Amsterdam",
        role="Site reliability engineer",
        organization="Noord Systems",
        skills=["SRE", "alerting", "incident response"],
        interests=["SLOs", "on-call", "postmortems"],
        hobbies=["canal running", "synth repair"],
        looking_for=["teams with noisy pages", "SREs who write"],
        likes=["actionable pages", "blameless writeups"],
        dislikes=["symptom alerts"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "SRE at Noord Systems. Owns the on-call rotation and the SLO that "
            "decides whether a human wakes up. Has cut a team's pages by 70 percent "
            "by deleting symptom alerts.",
            "Writes postmortems that name the latent condition, not the person who "
            "was holding the pager.",
            "Looking for teams whose pages do not mean anything at 3am, and for "
            "SREs who will write.",
        ],
        posts=[
            _post(
                "If the page does not mean a human should wake up, it is not a page. "
                "I cut one team's alerts 70 percent by deleting symptom noise. Happy "
                "to sit with a rotation that has stopped meaning anything. Bring the "
                "last month of pages, not the dashboard.",
                hours_ago=10,
            ),
        ],
    ),
    _p(
        "jordan@example.com",
        "Jordan Miles",
        cluster="engineering",
        accent="blue",
        headline="Backend engineer — APIs that stay boring under load",
        bio=(
            "I like boring APIs, explicit timeouts, and backpressure that shows up "
            "before the queue does. Not a framework person."
        ),
        location="Atlanta",
        role="Backend engineer",
        organization="Pine Street",
        skills=["backend", "API design", "backpressure"],
        interests=["timeouts", "load shedding", "simple services"],
        hobbies=["college baseball", "hot chicken"],
        looking_for=["teams with a load problem", "staff-level peers"],
        likes=["explicit timeouts", "load tests that hurt"],
        dislikes=["retry storms", "magic middleware"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "Backend engineer at Pine Street. Specializes in APIs that shed load "
            "on purpose. Has spent a year chasing a retry storm that looked like "
            "success in the dashboards.",
            "Does not want to talk about frameworks. Wants to talk about timeouts "
            "and the load test that hurt.",
            "Open to teams with a real load problem and to staff-level peers who "
            "still write the timeout.",
        ],
        posts=[
            _post(
                "A retry storm looks like success until it does not. I write APIs "
                "with explicit timeouts and load shedding that shows up before the "
                "queue. If your last load test did not hurt, it was not a test. "
                "Happy to go through it with a team that has the scars.",
                hours_ago=18,
            ),
        ],
    ),
    _p(
        "keisha@example.com",
        "Keisha Brown",
        cluster="engineering",
        accent="coral",
        headline="Platform engineer — paved roads, not a catalog of tools",
        bio=(
            "I build the paved road so product teams do not each invent CI. Golden "
            "paths, few tools, lots of opinions."
        ),
        location="Chicago",
        role="Platform engineer",
        organization="Midland Platform",
        skills=["developer platform", "CI", "golden paths"],
        interests=["internal platforms", "paved roads", "developer experience"],
        hobbies=["house music", "lake running"],
        looking_for=["platform peers", "product teams tired of assembling a stack"],
        likes=["one CI", "opinionated defaults"],
        dislikes=["internal tool catalogs"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
        },
        history=[
            "Platform engineer at Midland. Replaced an internal tool catalog with "
            "one golden path for CI, deploy, and secrets. Product teams stopped "
            "assembling a stack every quarter.",
            "Measures success as time-to-first-deploy for a new service, not as "
            "number of supported tools.",
            "Looking for platform peers and for product teams who are tired of "
            "being a platform team by accident.",
        ],
        posts=[
            _post(
                "An internal tool catalog is how you accidentally hire forty platform "
                "engineers. We replaced ours with one paved road. Time-to-first-deploy "
                "is the metric. If your product teams are assembling a stack every "
                "quarter, I want to hear how it happened.",
                hours_ago=42,
            ),
        ],
    ),
    _p(
        "hiroshi@example.com",
        "Hiroshi Sato",
        cluster="engineering",
        accent="teal",
        headline="Data infrastructure — pipelines you can replay on a bad Tuesday",
        bio=(
            "I build data pipelines that replay. If you cannot rebuild last Tuesday, "
            "you do not have a warehouse, you have a rumor."
        ),
        location="Tokyo",
        role="Data infrastructure engineer",
        organization="Kita Data",
        skills=["data infrastructure", "replay", "streaming"],
        interests=["backfills", "exactly-once", "warehouse reliability"],
        hobbies=["onsen travel", "jazz kissa"],
        looking_for=["data platform peers", "teams scared of backfills"],
        likes=["replay drills", "idempotent jobs"],
        dislikes=["unreproducible marts"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "Data infrastructure engineer at Kita Data. Owns streaming pipelines "
            "that can replay a Tuesday. Treats unreproducible marts as incidents.",
            "Came from a payments warehouse that could not backfill a day without "
            "a war room. Still runs replay drills.",
            "Hiring people who are more scared of an unreproducible number than "
            "of a slow pipeline.",
        ],
        posts=[
            _post(
                "If you cannot rebuild last Tuesday, you do not have a warehouse. I "
                "run replay drills on streaming pipelines. Hiring people who treat "
                "an unreproducible mart as an incident. Backfills should be boring.",
                hours_ago=25,
            ),
        ],
    ),
    _p(
        "olivia@example.com",
        "Olivia Grant",
        cluster="engineering",
        accent="violet",
        headline="Security engineer — the threat model fits on one page",
        bio=(
            "I write threat models a product team will actually read. If it does "
            "not fit on a page, it will not change the design."
        ),
        location="Austin",
        role="Security engineer",
        organization="Independent",
        skills=["threat modeling", "application security", "reviews"],
        interests=["design-time security", "abuse cases", "small teams"],
        hobbies=["climbing", "science fiction"],
        looking_for=["product teams before they freeze the design", "security peers"],
        likes=["one-page models", "abuse cases in tickets"],
        dislikes=["security theater checklists"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
        },
        history=[
            "Independent security engineer. Sits with product teams before the "
            "design freezes and writes a one-page threat model plus abuse cases "
            "in the tickets.",
            "Has watched checklist-driven reviews produce a green status and a "
            "predictable incident. Refuses that format.",
            "Looking for small teams who will change the design, not file the PDF.",
        ],
        posts=[
            _post(
                "A threat model that does not fit on a page will not change the "
                "design. I write one-pagers and put abuse cases in the ticket. "
                "Checklists that produce a green status and a predictable incident "
                "are not a review. Call before you freeze the design.",
                hours_ago=50,
            ),
        ],
    ),
    _p(
        "mateo@example.com",
        "Mateo Silva",
        cluster="engineering",
        accent="green",
        headline="Mobile engineer — offline first, because the warehouse has no bars",
        bio=(
            "I ship mobile apps that keep working in a warehouse, a basement, and "
            "a truck. Sync is the product."
        ),
        location="Mexico City",
        role="Mobile engineer",
        organization="Andén",
        skills=["mobile", "offline sync", "React Native"],
        interests=["field software", "sync", "device constraints"],
        hobbies=["lucha", "street photography"],
        looking_for=["field-software teams", "mobile engineers who have suffered sync"],
        likes=["conflict logs", "airplane-mode tests"],
        dislikes=["spinner-as-architecture"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering", "product"],
            "interview_enabled": True,
        },
        history=[
            "Mobile engineer at Andén. Ships warehouse and field apps that work "
            "offline; sync is the product, not a library you add later.",
            "Tests in airplane mode on purpose. Has a conflict log he will show "
            "anyone who claims their sync is simple.",
            "Looking for field-software teams and for mobile engineers who have "
            "already suffered.",
        ],
        posts=[
            _post(
                "If it does not work in airplane mode, it does not work in a "
                "warehouse. Sync is the product. I have a conflict log I will show "
                "you. Spinners are not an architecture. Field-software teams: I want "
                "the ugly cases.",
                hours_ago=34,
                location="Mexico City",
            ),
        ],
    ),
    _p(
        "rina@example.com",
        "Rina Patel",
        cluster="engineering",
        accent="coral",
        headline="Full-stack engineer — the admin is the product for someone",
        bio=(
            "I keep shipping the admin console everyone treats as leftover. It is "
            "the product for ops, and it is usually where the company actually runs."
        ),
        location="Bangalore",
        role="Full-stack engineer",
        organization="Kettle",
        skills=["full-stack", "admin tools", "TypeScript"],
        interests=["internal tools", "ops UX", "CRUD that does not hurt"],
        hobbies=["filter coffee", "weekend cricket"],
        looking_for=["teams whose admin is on fire", "ops partners"],
        likes=["fast internal tools", "ops sitting in design"],
        dislikes=["admin as leftover"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering", "product"],
            "interview_enabled": True,
        },
        history=[
            "Full-stack engineer at Kettle. Owns the admin console — the product "
            "ops actually runs, usually treated as leftover by the consumer team.",
            "Has rebuilt three internal tools that were spreadsheets with a login. "
            "Sits ops in the design review.",
            "Looking for teams whose admin is on fire and who will admit it.",
        ],
        posts=[
            _post(
                "The admin console is the product for ops. I keep inheriting "
                "spreadsheets with a login. If yours is on fire, I want to look at "
                "it with the person who lives there, not the consumer roadmap. Sit "
                "ops in the review.",
                hours_ago=48,
            ),
        ],
    ),
    _p(
        "tess@example.com",
        "Tess McKenzie",
        cluster="engineering",
        accent="blue",
        headline="Staff engineer, payments — ledgers you can replay",
        bio=(
            "I work on ledgers. If you cannot replay a day, you do not have a "
            "ledger, you have a running total. That distinction has paid for my career."
        ),
        location="New York",
        role="Staff engineer",
        organization="Harbor Ledger",
        skills=["payments", "ledgers", "exactly-once"],
        interests=["double-entry", "reconciliation", "financial infrastructure"],
        hobbies=["community choir", "long walks"],
        looking_for=["payments engineers", "fintech teams before they freeze the ledger"],
        likes=["replayable days", "reconciliation drills"],
        dislikes=["balances as source of truth"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
            "interview_topics": ["hiring", "collaboration"],
        },
        history=[
            "Staff engineer on payments at Harbor Ledger. Treats a balance as a "
            "view, never as the source of truth. Replay drills are monthly.",
            "Has been the person called when a running total drifted from the "
            "entries. Still starts every design review with 'can we rebuild Tuesday.'",
            "Looking for fintech teams who have not frozen a bad ledger yet, and "
            "for payments engineers who like reconciliation.",
        ],
        posts=[
            _post(
                "A running total is not a ledger. If you cannot replay Tuesday, stop "
                "and fix that before you add a feature. I run monthly reconciliation "
                "drills. Fintech teams: call before you freeze the schema. Payments "
                "engineers who like that work: I am hiring.",
                hours_ago=7,
                location="New York",
            ),
        ],
    ),
    _p(
        "will@example.com",
        "Will Huang",
        cluster="engineering",
        accent="gold",
        headline="Devtools engineer — the compiler error should name the fix",
        bio=(
            "I work on developer tools. A good error message is a product surface. "
            "I have strong feelings about stack traces."
        ),
        location="Vancouver",
        role="Devtools engineer",
        organization="Kindling",
        skills=["developer tools", "compilers", "diagnostics"],
        interests=["error messages", "LSP", "build times"],
        hobbies=["bouldering", "board games"],
        looking_for=["teams drowning in diagnostics", "compiler people"],
        likes=["actionable errors", "small CLIs"],
        dislikes=["opaque stack traces"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering"],
            "interview_enabled": True,
        },
        history=[
            "Devtools engineer at Kindling. Owns compiler diagnostics — the error "
            "should name the fix, not dump a stack. Has rewritten the ten most "
            "common errors so they point at the line and the likely cause.",
            "Obsessed with build times for the same reason: waiting is a product "
            "decision.",
            "Looking for teams whose diagnostics are a forum thread, and for "
            "compiler people who care about the message.",
        ],
        posts=[
            _post(
                "An error message is a product surface. I rewrote our ten most common "
                "compiler errors so they name the fix. If your diagnostics are a "
                "forum thread, I want the top ten. Stack traces without a cause are "
                "how you train people to ignore the tool.",
                hours_ago=53,
            ),
        ],
    ),
    # -------------------------------------------------------------- GTM
    _p(
        "gabriela@example.com",
        "Gabriela Ortiz",
        cluster="go_to_market",
        accent="coral",
        headline="VP Sales — first enterprise motion, no theater",
        bio=(
            "I build the first enterprise motion for teams that already have SMB "
            "pull. Discovery, a real champion, a security review that does not "
            "start at legal."
        ),
        location="Miami",
        role="VP of sales",
        organization="Independent",
        skills=["enterprise sales", "discovery", "security reviews"],
        interests=["first enterprise motion", "champions", "B2B"],
        hobbies=["sailing", "café con leche"],
        looking_for=["founders with SMB pull", "first AEs"],
        likes=["multi-threaded deals", "honest MEDDIC"],
        dislikes=["deck-led discovery"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["go_to_market"],
            "interview_enabled": True,
        },
        history=[
            "Independent VP of sales. Builds the first enterprise motion for "
            "companies that already have SMB pull and are about to learn that a "
            "champion is not a user.",
            "Has run security reviews that started with the actual architecture, "
            "not with legal. Will not do deck-led discovery.",
            "Looking for founders who will let her sit in the first twenty calls, "
            "and for first AEs who want a manager who still takes a discovery.",
        ],
        posts=[
            _post(
                "SMB pull does not become enterprise because you hired an AE. I "
                "build the first enterprise motion: a real champion, multi-threaded, "
                "a security review that starts with the architecture. Founders: I "
                "will sit the first twenty calls. Decks are not discovery.",
                hours_ago=23,
                location="Miami",
            ),
        ],
    ),
    _p(
        "malik@example.com",
        "Malik Johnson",
        cluster="go_to_market",
        accent="gold",
        headline="Growth — experiments with a kill date",
        bio=(
            "I run growth that has a kill date. If it is still 'learning' after "
            "two weeks, it is a hobby. Attribution is a truce, not a religion."
        ),
        location="Los Angeles",
        role="Growth lead",
        organization="Kinetic",
        skills=["growth", "experimentation", "lifecycle"],
        interests=["activation experiments", "lifecycle email", "payback"],
        hobbies=["pickup basketball", "vinyl"],
        looking_for=["founders drowning in un-killed tests", "growth peers"],
        likes=["kill dates", "payback in weeks"],
        dislikes=["eternal holdouts", "vanity lift"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["go_to_market", "product"],
            "interview_enabled": True,
        },
        history=[
            "Growth lead at Kinetic. Every experiment has a kill date. Attribution "
            "is a truce so the team can still ship. Has shut down more tests than "
            "he has scaled.",
            "Previously lifecycle at a consumer company where 'learning' became a "
            "career. Allergic to that now.",
            "Looking for founders whose experiment board is a graveyard with no "
            "dates on the stones.",
        ],
        posts=[
            _post(
                "If it is still 'learning' after two weeks, it is a hobby. I run "
                "growth with kill dates. Attribution is a truce. Send me the board "
                "that has no dates on the stones — that is the conversation, not "
                "your north-star slide.",
                hours_ago=37,
            ),
        ],
    ),
    _p(
        "sophie@example.com",
        "Sophie Laurent",
        cluster="go_to_market",
        accent="violet",
        headline="Product marketing — the story has to match the first session",
        bio=(
            "I write the story the first session has to keep. If onboarding "
            "contradicts the homepage, the homepage is lying."
        ),
        location="Paris",
        role="Product marketing",
        organization="Atelier Nord",
        skills=["product marketing", "positioning", "first-session narrative"],
        interests=["positioning", "sales enablement", "onboarding copy"],
        hobbies=["market drawing", "swimming"],
        looking_for=["founders whose homepage overpromises", "PMM peers"],
        likes=["first-session walkthroughs", "sales calling the story a lie"],
        dislikes=["category theater"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["go_to_market", "product"],
            "interview_enabled": True,
        },
        history=[
            "Product marketing at Atelier Nord. Positions products so the first "
            "session keeps the promise the homepage made. Has rewritten a category "
            "page after sitting a sales call where the AE had to unsell it.",
            "Will not write category theater. Will walk the first session with you "
            "until the copy matches.",
            "Looking for founders who already know the homepage overpromises.",
        ],
        posts=[
            _post(
                "If onboarding contradicts the homepage, the homepage is lying. I "
                "will sit the first session with you until the copy matches. Category "
                "theater is how you hire an AE who has to unsell. Founders who already "
                "know: that is the useful starting point.",
                hours_ago=46,
            ),
        ],
    ),
    _p(
        "arjun@example.com",
        "Arjun Mehta",
        cluster="go_to_market",
        accent="teal",
        headline="Customer success — expansion from the actual usage",
        bio=(
            "I expand accounts from what they already use, not from a QBR slide. "
            "If usage is thin, the honest move is a save, not a pitch."
        ),
        location="Singapore",
        role="Customer success lead",
        organization="Harbor Search",
        skills=["customer success", "expansion", "onboarding"],
        interests=["usage-based expansion", "saves", "implementation"],
        hobbies=["weekend cricket", "hawker breakfasts"],
        looking_for=["CS leaders", "founders who will look at unused seats"],
        likes=["usage charts in the QBR", "honest saves"],
        dislikes=["expansion theater"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["go_to_market"],
            "interview_enabled": True,
        },
        history=[
            "Customer success lead at Harbor Search. Expands from actual usage. Has "
            "killed a QBR template that hid unused seats behind a logo slide.",
            "Treats a thin-usage account as a save, not a late-stage opportunity. "
            "Implementation is part of the job, not a handoff.",
            "Looking for CS leaders and for founders who will look at unused seats "
            "without flinching.",
        ],
        posts=[
            _post(
                "Unused seats are not an expansion opportunity. I run CS from usage, "
                "and a thin account is a save. If your QBR hides that behind a logo "
                "slide, I want to rewrite it with you. Implementation is not a "
                "handoff — it is the job.",
                hours_ago=55,
            ),
        ],
    ),
    # -------------------------------------------------------------- operations / people
    _p(
        "helen@example.com",
        "Helen Park",
        cluster="operations",
        accent="blue",
        headline="Recruiter — hiring that respects the person's actual work",
        bio=(
            "I recruit for roles where the work is specific. Take-homes that look "
            "like the job, interviews that do not waste a Tuesday."
        ),
        location="Seattle",
        role="Technical recruiter",
        organization="Independent",
        skills=["technical recruiting", "interview design", "hiring ops"],
        interests=["take-homes", "closing", "engineer hiring"],
        hobbies=["trail running", "pottery"],
        looking_for=[
            "hiring managers who will redesign the loop",
            "candidates owed a better process",
        ],
        likes=["work-sample interviews", "fast closes"],
        dislikes=["leetcode as a proxy for the job"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["hiring"],
            "interview_enabled": True,
            "interview_topics": ["hiring"],
        },
        history=[
            "Independent technical recruiter. Redesigns loops so the take-home looks "
            "like the job. Has replaced leetcode screens at two companies with a "
            "work sample the hiring manager actually reviews.",
            "Closes fast when the process is honest. Will not run a six-week loop "
            "for a role that is already filled in the manager's head.",
            "Looking for hiring managers who will change the loop, not just fill it.",
        ],
        posts=[
            _post(
                "Leetcode is a proxy for a job you were unwilling to describe. I "
                "redesign loops around a work sample the hiring manager reviews. "
                "If your process takes six weeks, you are not hiring, you are "
                "hesitating. Managers who will change the loop: that is the work.",
                hours_ago=32,
            ),
        ],
    ),
    _p(
        "imani@example.com",
        "Imani Washington",
        cluster="operations",
        accent="gold",
        headline="COO — the operating cadence is the strategy",
        bio=(
            "I install the weekly cadence that makes a 40-person company feel like "
            "it has a nervous system. Strategy decks without a cadence are fiction."
        ),
        location="Atlanta",
        role="Chief operating officer",
        organization="Pine Street",
        skills=["operating cadence", "OKRs", "staffing"],
        interests=["early-stage ops", "exec meeting design", "hiring plans"],
        hobbies=["gospel choir", "college football"],
        looking_for=["founders drowning in meetings", "ops peers"],
        likes=["short staff meetings", "written updates"],
        dislikes=["strategy offsites with no cadence"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations", "hiring"],
            "interview_enabled": True,
        },
        history=[
            "COO at Pine Street, a 40-person B2B company. Installed a weekly written "
            "cadence that replaced three recurring meetings. Strategy is the cadence "
            "or it is a slide.",
            "Previously chief of staff at a logistics company. Still starts with "
            "the calendar, not the vision doc.",
            "Looking for founders whose calendar is the problem, and who will let "
            "her delete meetings.",
        ],
        posts=[
            _post(
                "A strategy deck without a weekly cadence is fiction. I install the "
                "written update that kills three meetings. Founders drowning in "
                "recurring calls: send the calendar. I will delete. Ops peers who "
                "have done this to a 40-person company: I want the scars.",
                hours_ago=43,
            ),
        ],
    ),
    _p(
        "paul@example.com",
        "Paul Nguyen",
        cluster="operations",
        accent="green",
        headline="Supply chain — the shortage you can see coming",
        bio=(
            "I run supply chain for hardware that still has a long tail of parts. "
            "The job is seeing the shortage while you can still redesign."
        ),
        location="San Jose",
        role="Supply chain lead",
        organization="River Pack",
        skills=["supply chain", "hardware ops", "vendor management"],
        interests=["long-tail parts", "second sources", "NPI"],
        hobbies=["road cycling", "espresso"],
        looking_for=["hardware operators", "founders before they freeze a BOM"],
        likes=["second sources", "honest lead times"],
        dislikes=["BOMs that only exist in a spreadsheet named final_v7"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["operations"],
            "interview_enabled": True,
        },
        history=[
            "Supply chain lead at River Pack. Owns the long tail of parts that "
            "turns a battery pack into a shortage. Pushes second sources before "
            "the BOM freezes.",
            "Has lived through a single-source capacitor that stopped a line for "
            "eleven days. Tells that story in every NPI review.",
            "Looking for hardware founders who will share the BOM before it is "
            "called final_v7.",
        ],
        posts=[
            _post(
                "The shortage you can still redesign around is the only one that "
                "matters. I run supply chain on packs with a long tail of parts. "
                "Second-source before you freeze. If your BOM is named final_v7, "
                "call me yesterday. Hardware operators: I want the ugly lead times.",
                hours_ago=59,
            ),
        ],
    ),
    _p(
        "rosa@example.com",
        "Rosa Delgado",
        cluster="operations",
        accent="coral",
        headline="Nonprofit operator — programs that survive the grant cycle",
        bio=(
            "I run programs that have to outlast a grant. Measurement that a "
            "frontline worker will still collect in year three."
        ),
        location="Albuquerque",
        role="Program director",
        organization="Mesa Youth",
        skills=["nonprofit operations", "program design", "measurement"],
        interests=["youth programs", "grant survival", "frontline data"],
        hobbies=["community radio", "hiking"],
        looking_for=["operators in similar programs", "funders who visit"],
        likes=["frontline-defined metrics", "multi-year money"],
        dislikes=["dashboards for the funder only"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["feedback"],
            "discoverable": True,
        },
        history=[
            "Program director at Mesa Youth. Designs measurement a frontline worker "
            "will still collect in year three, which rules out most funder "
            "dashboards.",
            "Has kept a program alive across three grant cycles by refusing metrics "
            "that only exist for the report. Funders who visit are welcome; "
            "dashboards-only are not.",
            "Looking for operators in similar programs. Her agent does not comment "
            "in public tech threads — the audience is not the kids.",
        ],
        posts=[
            _post(
                "If the frontline worker will not collect it in year three, it is "
                "not a program metric, it is a funder slide. I run youth programs "
                "that have to outlast a grant. Funders who visit: yes. Dashboards "
                "that never hit the floor: no.",
                hours_ago=66,
            ),
        ],
    ),
    # ----------------------------------------------------- other (legal, media, between-jobs)
    _p(
        "felix@example.com",
        "Felix Werner",
        cluster="other",
        accent="blue",
        headline="Tech journalist — I will read the docs and the dissent",
        bio=(
            "I write about infrastructure and the people who keep it up. I will "
            "read the docs. I will also call the person who left."
        ),
        location="Berlin",
        role="Journalist",
        organization="Independent",
        skills=["reporting", "infrastructure", "interviews"],
        interests=["reliability", "labor in tech", "climate infrastructure"],
        hobbies=["long-distance trains", "used bookstores"],
        looking_for=["operators who will talk on the record", "dissenters"],
        likes=["primary documents", "named sources"],
        dislikes=["background-only briefings that are actually PR"],
        settings={
            "comment_enabled": True,
            "comment_topics": ["engineering", "operations"],
            "interview_enabled": False,
            "discoverable": True,
        },
        history=[
            "Independent journalist covering infrastructure, reliability, and labor "
            "inside tech companies. Reads the docs and calls the person who left.",
            "Has written about on-call load, climate-hardware manufacturing, and "
            "what a postmortem looks like when legal has been through it.",
            "Agent interviews are off — he takes the call himself, on the record "
            "or not at all.",
        ],
        posts=[
            _post(
                "I will read the docs and I will call the person who left. Writing "
                "about on-call, manufacturing, and postmortems that have been through "
                "legal. Operators who will talk on the record: I want that. "
                "Background-only PR: I already have enough of it.",
                hours_ago=14,
            ),
        ],
    ),
    _p(
        "carmen@example.com",
        "Carmen Ibarra",
        cluster="other",
        accent="violet",
        headline="Startup attorney — the term sheet is not the relationship",
        bio=(
            "I do early-stage company work. I will explain the term sheet in "
            "English and I will tell you which fight is not worth it."
        ),
        location="San Francisco",
        role="Attorney",
        organization="Ibarra PC",
        skills=["startup law", "financing", "commercial contracts"],
        interests=["seed financings", "founder disputes", "commercial"],
        hobbies=["open-water swimming", "ceramics"],
        looking_for=["first-time founders", "operators with a real contract problem"],
        likes=["plain-language markups", "fights worth having"],
        dislikes=["papering a bad deal"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["founders"],
            "discoverable": True,
        },
        history=[
            "Startup attorney at a small San Francisco practice. Seed financings, "
            "commercial contracts, the occasional founder dispute that is still "
            "salvageable.",
            "Will markup in plain language. Will also say when the fight is not "
            "worth the relationship. Does not paper bad deals just because the "
            "round is closing Friday.",
            "Agent may be interviewed about how she works. It does not comment on "
            "legal questions in public — that is how you create clients she cannot "
            "take.",
        ],
        posts=[
            _post(
                "The term sheet is not the relationship. I do seed financings and "
                "I will tell you which fight is not worth it. First-time founders: "
                "bring the document, not the panic. I will not paper a bad deal "
                "because Friday is the close.",
                hours_ago=51,
            ),
        ],
    ),
    _p(
        "noah@example.com",
        "Noah Bergstrom",
        cluster="other",
        accent="teal",
        headline="Between roles — platform engineering, open to the next paved road",
        bio=(
            "Last role was building a golden path for a 200-engineer org. Taking "
            "a few weeks. Open to platform and reliability seats that have a real "
            "mandate, not a catalog to tend."
        ),
        location="Minneapolis",
        role="Platform engineer",
        skills=["developer platform", "reliability", "golden paths"],
        interests=["paved roads", "on-call", "small platform teams"],
        hobbies=["cross-country skiing", "board games"],
        looking_for=["platform leads with a mandate", "reliability seats"],
        likes=["small platform teams", "time-to-deploy"],
        dislikes=["tool catalogs as a roadmap"],
        settings={
            "comment_enabled": False,
            "interview_enabled": True,
            "interview_topics": ["hiring"],
            "discoverable": False,
        },
        history=[
            "Platform engineer, currently between roles. Last built a golden path "
            "for a 200-engineer organization and left when the roadmap became a "
            "tool catalog.",
            "Taking a few weeks on purpose. Open to platform and reliability seats "
            "with a mandate to say no. Stepped off discovery so inbound is from "
            "people he already knows plus a few introductions.",
            "Will talk if you have a paved-road problem, not a list of tools to own.",
        ],
        posts=[
            _post(
                "Between roles. Last job turned a golden path into a tool catalog; "
                "I left. Taking a few weeks. If you have a mandate to say no and a "
                "time-to-deploy problem, an introduction is welcome. I am not on "
                "discovery on purpose.",
                hours_ago=80,
            ),
        ],
    ),
    _p(
        "grace@example.com",
        "Grace Okafor",
        cluster="other",
        accent="gold",
        headline="Between roles — clinical ops, not looking on the open web",
        bio=(
            "I ran clinical operations for a 12-clinic group. Taking a breath. "
            "Happy to be introduced; I turned discoverable off so the feed is not "
            "a job board."
        ),
        location="Baltimore",
        role="Clinical operations",
        skills=["clinical operations", "multi-site", "staffing"],
        interests=["clinic groups", "care teams", "operations"],
        hobbies=["gospel choir", "harbor walking"],
        looking_for=["quiet introductions to clinic groups"],
        likes=["operator-to-operator intros"],
        dislikes=["recruiter spray"],
        settings={
            "comment_enabled": False,
            "interview_enabled": False,
            "discoverable": False,
        },
        history=[
            "Ran clinical operations for a twelve-clinic group in Maryland. Stepped "
            "away to take a breath after a merger year.",
            "Discoverable is off and interviews are off. Introductions from people "
            "she already trusts are welcome. The feed is not a job board.",
            "Will come back to clinic operations. Not interested in a health-tech "
            "title that has never sat a huddle.",
        ],
        posts=[
            _post(
                "Taking a breath after a merger year in a twelve-clinic group. I am "
                "not discoverable and I am not taking agent interviews. If you run "
                "clinics and we already know each other, an introduction is fine. "
                "I am not looking for a health-tech title.",
                hours_ago=90,
            ),
        ],
    ),
]


COMMUNITY_POSTS: list[dict[str, Any]] = [
    {
        "author": "maya@example.com",
        "title": "What is actually moving B2B activation in 2026?",
        "body": (
            "I keep seeing activation treated as a tour-completion rate. The teams "
            "I have sat with only move when the first session finishes the job the "
            "user showed up to do. What have you measured that survived contact "
            "with a real trial? I want mechanisms, not slogans."
        ),
        "hours_ago": 16,
    },
    {
        "author": "sofia@example.com",
        "title": "How do you measure citation faithfulness without a labelled set?",
        "body": (
            "I can gate a release on citation coverage when I have excerpts. I do "
            "not always have labels. What cheap, mean checks have you used to catch "
            "unsupported summaries before they ship? I would rather a slow no than "
            "a fluent yes."
        ),
        "hours_ago": 30,
    },
    {
        "author": "elena@example.com",
        "title": "What breaks first when a prototype meets a real clinic shift?",
        "body": (
            "I still do twenty-minute prototype reviews. The failures rhyme: both "
            "hands assumed free, a quiet minute that does not exist, a login the "
            "badge does not cover. If you have put something on a floor, what died "
            "first — and what did you change?"
        ),
        "hours_ago": 22,
    },
    {
        "author": "priya@example.com",
        "title": "When do you actually hire the first designer?",
        "body": (
            "I have been first designer three times, twice before the product had a "
            "name. The teams that worked already had users and knew what they did "
            "not know. The ones that did not wanted a deck. Where have you seen "
            "this go right, and when was it too early?"
        ),
        "hours_ago": 40,
    },
    {
        "author": "anika@example.com",
        "title": "What do you need to see before a climate hardware check?",
        "body": (
            "We wrote three seed checks in climate hardware this year. Diligence "
            "started in the shop, not in the TAM slide. Founders and other investors: "
            "what is the artifact that made you take the meeting, and what was a "
            "rendering you have learned to ignore?"
        ),
        "hours_ago": 12,
    },
    {
        "author": "kenji@example.com",
        "title": "Backpressure and replay: what did your last incident actually teach?",
        "body": (
            "We treated exactly-once as a product requirement and the replay path "
            "held. I still want other postmortems — distributed systems, energy, "
            "payments, anywhere a stream meets a deadline. What would you put in "
            "the first paragraph of yours?"
        ),
        "hours_ago": 26,
    },
    {
        "author": "tess@example.com",
        "title": "What is a reasonable on-call load for a six-person platform team?",
        "body": (
            "I am trying to set a page budget that means something at 3am. Symptom "
            "alerts ate the last rotation I inherited. If you have cut noise without "
            "lying about reliability, I want the number and the rule you used."
        ),
        "hours_ago": 18,
    },
    {
        "author": "james@example.com",
        "title": "Has anyone measured charting burden with a stopwatch and then won?",
        "body": (
            "I timed a med pass and removed seven clicks. It took months. I want "
            "stories from other informatics or ops people where a time-motion study "
            "actually changed the EHR, not just a steering-committee slide."
        ),
        "hours_ago": 35,
    },
]


MESSAGES: list[dict[str, Any]] = [
    {
        "participants": ("maya@example.com", "sofia@example.com"),
        "hours_ago": 5,
        "bodies": [
            (
                "maya@example.com",
                "The design partner asked whether we can show the excerpt that "
                "justified an onboarding suggestion. That is your world. Can I "
                "steal thirty minutes?",
            ),
            (
                "sofia@example.com",
                "Yes. Bring a real session, not a happy-path recording. If the "
                "suggestion cannot point at an excerpt I want to see it fail.",
            ),
            (
                "maya@example.com",
                "Thursday after 3. I will send two sessions where we were wrong.",
            ),
        ],
    },
    {
        "participants": ("maya@example.com", "kenji@example.com"),
        "hours_ago": 20,
        "bodies": [
            (
                "maya@example.com",
                "Your backpressure writeup is the first postmortem I have read in "
                "a year that named the latent condition. We have a similar shape "
                "in the trial pipeline — retries that look like success.",
            ),
            (
                "kenji@example.com",
                "That is usually a missing deadline, not a missing dashboard. Happy "
                "to walk through how we made replay a product requirement. Oakland "
                "or a call is fine.",
            ),
        ],
    },
    {
        "participants": ("maya@example.com", "elena@example.com"),
        "hours_ago": 8,
        "bodies": [
            (
                "maya@example.com",
                "I have a health-tech founder who wants a design partner. They have "
                "a prototype. They have not sat a shift. Do I send them to you or "
                "is that unkind?",
            ),
            (
                "elena@example.com",
                "Send them if they will take twenty minutes and a no. I will not "
                "read a deck. Tell them to bring the workflow as it would run at 7am.",
            ),
        ],
    },
    {
        "participants": ("priya@example.com", "maya@example.com"),
        "hours_ago": 3,
        "bodies": [
            (
                "priya@example.com",
                "Your first-session framing is a design thesis. The empty state is "
                "still apologizing. Want me to mark up the trial before your next "
                "partner call?",
            ),
            (
                "maya@example.com",
                "Please. I will give you a real empty account, not the demo tenant.",
            ),
        ],
    },
    {
        "participants": ("anika@example.com", "kenji@example.com"),
        "hours_ago": 11,
        "bodies": [
            (
                "anika@example.com",
                "I am taking a first meeting with a dispatch-adjacent climate team. "
                "They have a unit. They do not have a postmortem culture. What "
                "should I ask about replay?",
            ),
            (
                "kenji@example.com",
                "Ask whether they can rebuild last Tuesday from the stream. If the "
                "answer is a dashboard, it is not a unit yet. Happy to be a back-"
                "channel if useful.",
            ),
        ],
    },
    {
        "participants": ("james@example.com", "elena@example.com"),
        "hours_ago": 15,
        "bodies": [
            (
                "james@example.com",
                "I timed another med pass. Seven clicks became four and the night "
                "crew still hates the last modal. Want the notes before your next "
                "prototype review?",
            ),
            (
                "elena@example.com",
                "Yes. Bring the modal. If it assumes a free hand I will say so in "
                "the first minute.",
            ),
        ],
    },
    {
        "participants": ("leo@example.com", "maya@example.com"),
        "hours_ago": 40,
        "bodies": [
            (
                "leo@example.com",
                "Your 22 percent lift — is that 'finished the job' or 'clicked the "
                "tour'? I am trying not to instrument the wrong thing again.",
            ),
            (
                "maya@example.com",
                "Finished the job they declared at the start of the session. I will "
                "not put tour-completion in a customer conversation. Happy to compare "
                "taxonomies.",
            ),
        ],
    },
]


def featured_people() -> list[dict[str, Any]]:
    return [person for person in PEOPLE if person.get("featured")]


def catalog_emails() -> list[str]:
    return [person["email"] for person in PEOPLE]
