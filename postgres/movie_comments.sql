create table movie_comments (
  id integer generated always as identity primary key,
  user_id integer not null
    references users(id) on delete cascade,
  movie_id integer not null,
  body text not null,
  created_at timestamptz not null default now(),

  constraint movie_comments_movie_id_check
    check (movie_id > 0),

  constraint movie_comments_body_check
    check (
      char_length(body) between 1 and 2000
      and body ~ '[^[:space:]]'
    )
);

create index movie_comments_movie_created_idx
  on movie_comments (movie_id, created_at desc, id desc);

create index movie_comments_user_id_idx
  on movie_comments (user_id);