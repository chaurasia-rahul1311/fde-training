from app.db import save_user_to_db
from app.models import UserContext


def choose(prompt: str, options: list[str]) -> str:
    print(prompt)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")
    while True:
        raw = input("Select a number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"Enter a number from 1 to {len(options)}.")


def main() -> None:
    full_name = input("Enter the full name: ").strip()
    role = choose("Select a role:", ["viewer", "editor", "admin"])
    is_authenticated = (
        choose("Is the user authenticated?", ["yes", "no"]) == "yes"
    )

    try:
        user = UserContext(
            full_name=full_name,
            role=role,
            is_authenticated=is_authenticated,
        )
        print(save_user_to_db(user))
    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
