from typing import Any

from .db import _transaction
from .profile_photos import profile_photo_url


def list_movie_nights(user_id: int) -> list[dict[str, Any]]:
    with _transaction() as cursor:
        cursor.execute(
            """
            select invitation.id, movie_id, event_summary, starts_at,
                   location, message, participant.username,
                   invitation.friend_user_id = %s, response, participant.id,
                   participant.first_name, participant.last_name
            from movie_invitations invitation
            join users participant on participant.id = case
                when invitation.friend_user_id = %s then invitation.created_by_user_id
                else invitation.friend_user_id
            end
            where (invitation.friend_user_id = %s or invitation.created_by_user_id = %s)
              and invitation.status = 'sent'
              and invitation.starts_at > current_timestamp
            order by invitation.starts_at, invitation.id
            """,
            (user_id, user_id, user_id, user_id),
        )
        rows = cursor.fetchall()

    photo_urls = {user_id: profile_photo_url(user_id) for user_id in {row[9] for row in rows}}
    return [
        {
            "id": row[0],
            "movieId": row[1],
            "eventSummary": row[2],
            "startsAt": row[3].isoformat(),
            "location": row[4],
            "message": row[5],
            "friendName": " ".join(filter(None, row[10:12])) or row[6],
            "friendProfilePhotoUrl": photo_urls[row[9]],
            "incoming": row[7],
            "response": row[8],
        }
        for row in rows
    ]


def respond_to_movie_night(user_id: int, invitation_id: int, decision: str) -> bool:
    if decision not in ("accepted", "declined"):
        raise RuntimeError("Choose accept or decline.")
    with _transaction() as cursor:
        cursor.execute(
            """
            update movie_invitations
            set response = %s, updated_at = current_timestamp
            where id = %s and friend_user_id = %s and status = 'sent'
              and starts_at > current_timestamp and response = 'awaiting'
            """,
            (decision, invitation_id, user_id),
        )
        return cursor.rowcount == 1
