import openai
import os



MODEL = "gpt-4"


def make_chat_gpt_request(data):
    chat_data = data.model_dump()
    organization_id = db.get_user(user_id).get("org_id")

    additional_context = chat_data.get("context")
    project_members = chat_data.get("project_members")
    project = chat_data.get("project")

    all_details = db.get_all_details(org_id=organization_id, user_id=user_id)
    projects = all_details.get("projects")
    employee_assignments = all_details.get("employee_assignments")
    team_roles = all_details.get("team_roles")

    system_message = (
    )

    user_message = (f"The manager of the project himself has also sent a comment: '{additional_context}'."
                    "Do your best to satisfy his preferences when assembling your team"
                    "Make sure not to return more users than required roles")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )