from datetime import datetime


def greet(name: str) -> str:
    if not name.strip():
        raise ValueError("Name cannot be empty")
    return f"Labas, {name}! ({datetime.now().year})"


if __name__ == "__main__":
    user = input("Ivesk varda: ")
    print(greet(user))
