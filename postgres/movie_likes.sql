create table movie_likes (
    user_id integer not null references users(id) on delete cascade,
    movie_id integer not null,
    created_at timestamptz not null default now(),
    primary key (user_id, movie_id)
  );

  create index movie_likes_movie_id_idx on movie_likes (movie_id);