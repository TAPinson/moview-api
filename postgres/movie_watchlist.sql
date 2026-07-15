create table movie_watchlist (
  user_id integer not null references users(id) on delete cascade,
  movie_id integer not null,
  status varchar not null default 'want_to_watch',
  added_at timestamptz not null default now(),
  watched_at timestamptz,
  notes text,
  primary key (user_id, movie_id)
);

create index movie_watchlist_user_status_idx
  on movie_watchlist (user_id, status);

create index movie_watchlist_movie_id_idx
  on movie_watchlist (movie_id);