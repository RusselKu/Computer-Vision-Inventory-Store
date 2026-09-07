import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://klsqlozvtgqsruwfrkss.supabase.co';
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtsc3Fsb3p2dGdxc3J1d2Zya3NzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg1NTk2NjUsImV4cCI6MjEwNDEzNTY2NX0.llyR5BzDC6QT8OKhXXWkRZn9lwN5GB96oH6fRtQLYYk';

export const supabase = createClient(supabaseUrl, supabaseKey);