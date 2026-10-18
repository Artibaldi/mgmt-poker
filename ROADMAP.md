# Roadmap

Management Poker grows in small stages. Done stages are in the [changelog](CHANGELOG.md).

## Now

- Run the first online sessions and tune signal thresholds, card wording and role weights from the results.
- Quality journal: facts marked “inaccurate” at the table feed back into the generator.
- A month-to-month comparison in the summary: last time's averages next to this time's.

## Next

- **Jira Cloud:** filtering by `accountId`.
- Signals from meeting notes: mentions, decisions and promises made by the person.
- Hard-skill signals from Jira: returns to an earlier status, reopened issues, linked defects.
- HTTPS out of the box for the relay (self-signed or corporate certificate).
- A deck generator that drafts cards from `signals.json` without an LLM, for review by the manager.

## Later

- An English interface.
- Custom competence models: your own suits and clusters per role.
- Confluence as a source: pages the person authored or reviewed in the period.

## Will not do

- A leaderboard or any comparison of people.
- Writing estimates, notes or results to Jira, HR systems or any shared storage.
- Storing data about real people in the repository.
