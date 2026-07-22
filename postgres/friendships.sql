begin;

  create table friendships (
    user_low_id integer not null
      references users(id)
      on delete cascade,

    user_high_id integer not null
      references users(id)
      on delete cascade,

    requested_by_user_id integer not null
      references users(id)
      on delete cascade,

    status varchar(20) not null default 'pending',

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    primary key (user_low_id, user_high_id),

    constraint friendships_user_order_check
      check (user_low_id < user_high_id),

    constraint friendships_requester_check
      check (
        requested_by_user_id = user_low_id
        or requested_by_user_id = user_high_id
      ),

    constraint friendships_status_check
      check (status in ('pending', 'accepted'))
  );

  create index friendships_user_high_id_idx
    on friendships (user_high_id);

  create index friendships_pending_requester_idx
    on friendships (requested_by_user_id)
    where status = 'pending';

  create index friendships_pending_low_user_idx
    on friendships (user_low_id)
    where status = 'pending';

  create index friendships_pending_high_user_idx
    on friendships (user_high_id)
    where status = 'pending';

  create index friendships_accepted_low_user_idx
    on friendships (user_low_id)
    where status = 'accepted';

  create index friendships_accepted_high_user_idx
    on friendships (user_high_id)
    where status = 'accepted';

  commit;
