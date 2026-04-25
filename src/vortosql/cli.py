from typing import Any

from vortosql.app import DEPARTMENTS, NL2SQLApp

DIVIDER = "─" * 60


def _format_table(columns: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "  (no results)"
    col_widths = [
        max(len(str(col)), max(len(str(row[i])) for row in rows))
        for i, col in enumerate(columns)
    ]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = (
        "|" + "|".join(f" {col:<{w}} " for col, w in zip(columns, col_widths)) + "|"
    )
    body = "\n".join(
        "|" + "|".join(f" {str(v):<{w}} " for v, w in zip(row, col_widths)) + "|"
        for row in rows
    )
    return f"{sep}\n{header}\n{sep}\n{body}\n{sep}"


def _pick_department() -> str | None:
    options = DEPARTMENTS + ["Random"]
    print("\nSelect a department:")
    for i, d in enumerate(options, 1):
        print(f"  [{i}] {d}")
    while True:
        try:
            choice = input("\nChoice (1-4): ").strip()
        except EOFError, KeyboardInterrupt:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            selected = options[int(choice) - 1]
            return None if selected == "Random" else selected
        print("  Invalid choice, try again.")


def main() -> None:
    print(f"\n{'NL2SQL Data Agent':^60}")
    print(DIVIDER)

    department = _pick_department()
    app = NL2SQLApp(department=department)

    print(f"\n  Department : {app.department}")
    print(f"  Scope      : queries restricted to {app.department} only")
    print(f"\n{DIVIDER}")
    print('  Ask a question or type "exit" to quit.')
    print(DIVIDER)

    while True:
        try:
            question = input("\n> ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("\nGoodbye!")
            break

        result = app.ask(question)

        early_stop = result.get("pipeline_early_stop")
        if early_stop:
            print(f"\n  ! {early_stop}")
            print(f"\n{DIVIDER}")
            continue

        error = result.get("sql_executor_error")
        if error:
            print(f"\n  ! Error: {error}")
            print(f"\n{DIVIDER}")
            continue

        sql = result.get("sql_executor_sql_query", "")
        columns = result.get("sql_executor_columns", [])
        rows = result.get("sql_executor_rows", [])
        row_count = result.get("sql_executor_row_count", 0)
        latency = result.get("pipeline_latency", 0)

        answer = result.get("answer_generator_answer")
        if answer:
            print(f"\n  {answer}")

        print(f"\n  SQL  : {sql}\n")
        if row_count == 0:
            print("  No results found.")
        else:
            print(_format_table(columns, rows))
            print(f"\n  {row_count} row(s)  ·  {latency:.2f}s")
        print(f"\n{DIVIDER}")


if __name__ == "__main__":
    main()
