begin;

create table movie_invitations (
  id integer generated always as identity primary key,

  uid varchar(255) not null unique,

  created_by_user_id integer not null
    references users(id)
    on delete cascade,

  friend_user_id integer not null
    references users(id)
    on delete cascade,

  movie_id integer not null,

  starts_at timestamptz not null,
  ends_at timestamptz not null,
  timezone varchar(255) not null,

  event_summary varchar(255) not null,
  location text,
  message text,

  calendar_sequence integer not null default 0,

  status varchar(20) not null default 'pending',
  idempotency_key varchar(255) not null,

  provider_message_id varchar(255),
  error_message text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  sent_at timestamptz,
  cancelled_at timestamptz,

  constraint movie_invitations_distinct_users_check
    check (created_by_user_id <> friend_user_id),

  constraint movie_invitations_time_order_check
    check (ends_at > starts_at),

  constraint movie_invitations_sequence_check
    check (calendar_sequence >= 0),

  constraint movie_invitations_status_check
    check (
      status in (
        'pending',
        'sending',
        'sent',
        'failed',
        'cancelled'
      )
    ),

  constraint movie_invitations_idempotency_unique
    unique (created_by_user_id, idempotency_key)
);

create index movie_invitations_creator_start_idx
  on movie_invitations (created_by_user_id, starts_at desc);

create index movie_invitations_friend_start_idx
  on movie_invitations (friend_user_id, starts_at desc);

create index movie_invitations_movie_id_idx
  on movie_invitations (movie_id);

create index movie_invitations_pending_idx
  on movie_invitations (created_at)
  where status in ('pending', 'failed');

commit;
