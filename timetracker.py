import click
import pendulum
import requests
from requests.auth import HTTPBasicAuth
from toolz import groupby, valmap


def get_entries(token, start, end):
    start_date = start.set(hour=0, minute=0, second=0, microsecond=0)
    end_date = end.set(hour=0, minute=0, second=0, microsecond=0)
    entries = requests.get(
        "https://api.track.toggl.com/api/v9/me/time_entries",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        auth=HTTPBasicAuth(token, "api_token"),
    ).json()
    return entries


def get_projects(token, entries):
    projects = {}
    for e in entries:
        pid = e.get("pid")
        wid = e.get("wid")

        if pid is None or wid is None:
            continue

        project_info = get_project(pid, wid, token)
        projects[pid] = project_info["name"]

    return projects


def get_project(id, wid, token):
    project = requests.get(
        f"https://api.track.toggl.com/api/v9/workspaces/{wid}/projects/{id}",
        auth=HTTPBasicAuth(token, "api_token"),
    )
    return project.json()


def summarize(entries, projects, timezone):
    mod_entries = [
        {
            "date": pendulum.parse(e["start"])
            .in_timezone(timezone)
            .format("YYYY-MM-DD"),
            **e,
        }
        for e in entries
    ]
    summary = valmap(
        lambda e: sum(map(lambda i: i["duration"], e)),
        groupby(
            key=lambda x: (x["date"], x.get("pid"), x.get("description")),
            seq=mod_entries,
        ),
    )
    formated_summaries = [
        {
            "date": k[0],
            "project": projects.get(k[1]),
            "description": k[2],
            "duration": v,
        }
        for k, v in summary.items()
    ]
    return groupby("date", formated_summaries)


def format_report(date, summary):
    r = f"checkin {date}\n"
    for entry in summary:
        project = entry["project"] if entry["project"] else "no-project"
        description = entry["description"]
        duration_hrs = entry["duration"] / 3600
        if duration_hrs < 0:
            click.echo(
                f"WARN: Got negative time for {description}. There might be a running timer"
            )
        r += f"- {duration_hrs:.2f} {'hrs' if duration_hrs>1.0 else 'hr'} #{project.lower()} {description}\n"
    return r


@click.command()
@click.option("--since", type=str)
@click.option("-y", "--yesterday", is_flag=True)
@click.option("-w", "--week", is_flag=True)
@click.option("-l", "--lastweek", is_flag=True)
@click.option("--token", type=str)
@click.option("--timezone", type=str, default="Asia/Singapore")
def main(since, token, timezone, yesterday, week, lastweek):
    if token is None or token == "":
        raise click.BadOptionUsage("token", "Token variable is needed")
    now = pendulum.now(timezone)
    if since:
        start = pendulum.parse(since).set(tz=timezone)
    elif yesterday:
        start = now.subtract(days=1)
    elif week:
        start = now.start_of("week")
    elif lastweek:
        start = now.subtract(weeks=1).start_of("week")
    else:
        start = now
    end = now.add(days=1)
    click.echo(
        f"Getting entries starting from {start.to_date_string()} to {end.subtract(days=1).to_date_string()}"
    )
    entries = get_entries(token, start, end)
    projects = get_projects(token, entries)
    summaries = summarize(entries, projects, timezone)
    for date, summary in summaries.items():
        click.echo(format_report(date, summary))


if "__main__" == __name__:
    main(auto_envvar_prefix="TIMETRACKER")
