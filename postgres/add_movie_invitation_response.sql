alter table movie_invitations
  add column response text not null default 'awaiting'
  check (response in ('awaiting', 'accepted', 'declined'));
