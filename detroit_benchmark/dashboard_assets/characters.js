/* The three Characters, lowercase, in one place for every dashboard script. */
const CHARACTERS = Object.freeze(['connor', 'kara', 'markus']);
/* A Character's key ('connor', 'kara', 'markus'), or null for anyone else. */
const characterKey = character => {
  const key = String(character || '').toLowerCase();
  return CHARACTERS.includes(key) ? key : null;
};
