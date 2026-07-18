import streamlit as st
import csv
import io
import time
import praw
from praw.exceptions import RedditAPIException
from datetime import datetime, timezone

# Page configuration
st.set_page_config(page_title="Reddit Thread Finder", page_icon="🔍", layout="wide")

st.title("🔍 Reddit Topic Thread Finder & Exporter")
st.markdown("Search intersecting Reddit discussions and export the results to CSV. *(Data is fetched live, filtered for safety, and not stored).*")

# --- Initialize PRAW (Reddit API Wrapper) ---
@st.cache_resource
def get_reddit_client():
    client_id = st.secrets.get("REDDIT_CLIENT_ID", "")
    client_secret = st.secrets.get("REDDIT_CLIENT_SECRET", "")
    user_agent = st.secrets.get("REDDIT_USER_AGENT", "linux:reddit-thread-finder:v1.0")
    
    if not client_id or not client_secret:
        st.error("⚠️ Reddit API credentials missing in Streamlit Secrets. Please add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.")
        st.stop()
        
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent
    )

reddit = get_reddit_client()

# --- Sidebar for Inputs ---
with st.sidebar:
    st.header("Search Parameters")
    main_topic = st.text_input("Main Topic *", placeholder="e.g., Machine Learning")
    
    st.subheader("Advanced Options")
    sec_topic1 = st.text_input("Secondary Topic 1 (Optional)", placeholder="e.g., Ethics")
    sec_topic2 = st.text_input("Secondary Topic 2 (Optional)", placeholder="e.g., Jobs")
    sec_topic3 = st.text_input("Secondary Topic 3 (Optional)", placeholder="e.g., Open Source")
    
    target_subreddit = st.text_input("Restrict to Subreddit (Optional)", placeholder="e.g., MachineLearning")
    
    # SAFEGUARD 1: NSFW Filtering (Default OFF for safety and compliance)
    include_nsfw = st.checkbox("Include NSFW results", value=False, help="Keep this off to ensure safe-for-work results.")
    include_comments = st.checkbox("Include Top 3 Comments (Slower)", value=False)
    
    sort_by = st.selectbox("Sort By", ["relevance", "top", "new", "comments"], index=0)
    time_filter = st.selectbox("Time Range", ["all", "year", "month", "week", "day"], index=1)
    
    # SAFEGUARD 2: Hard cap on results to prevent massive API payloads
    limit = st.slider("Max Results", min_value=5, max_value=25, value=10, step=5)
    
    search_btn = st.button("🔍 Search & Generate CSV", type="primary", use_container_width=True)

# --- Main Search Logic ---
if search_btn or 'search_results' in st.session_state:
    if not main_topic or not main_topic.strip():
        st.warning("⚠️ Please enter at least a main topic.")
    else:
        # SAFEGUARD 3: User Session Cooldown (Prevent button spamming)
        current_time = time.time()
        if 'last_search_time' in st.session_state:
            time_since_last_search = current_time - st.session_state['last_search_time']
            if time_since_last_search < 3.0: # 3-second cooldown
                st.warning("⏳ Please wait a few seconds before searching again to protect the API.")
                st.stop()
        
        with st.spinner("Searching Reddit via official API..."):
            # Build boolean query
            q = f'"{main_topic.strip()}"'
            secondary_topics = [t.strip() for t in [sec_topic1, sec_topic2, sec_topic3] if t and t.strip()]
            if secondary_topics:
                parts = [f'"{t}"' for t in secondary_topics]
                q += f' AND ({" OR ".join(parts)})'
            
            try:
                # Determine which subreddit to search
                if target_subreddit and target_subreddit.strip():
                    clean_sub = target_subreddit.strip().replace('r/', '')
                    subreddit_obj = reddit.subreddit(clean_sub)
                else:
                    subreddit_obj = reddit.subreddit('all')
                
                # Execute search
                results = subreddit_obj.search(
                    query=q,
                    sort=sort_by,
                    time_filter=time_filter,
                    limit=limit
                )
                
                markdown_results = []
                csv_rows = []
                found_any = False
                
                for post in results:
                    # SAFEGUARD 1 (Applied): Skip NSFW posts if the user didn't explicitly opt-in
                    if post.over_18 and not include_nsfw:
                        continue
                        
                    found_any = True
                    created_date = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).strftime('%Y-%m-%d')
                    
                    comments_text = "N/A"
                    if include_comments:
                        try:
                            # Fetch comments efficiently (limit=0 prevents fetching deep nested trees, saving API calls)
                            post.comments.replace_more(limit=0)
                            top_comments = sorted(post.comments, key=lambda c: c.score, reverse=True)[:3]
                            comment_strs = []
                            for c in top_comments:
                                author = c.author.name if c.author else "[deleted]"
                                body = c.body.replace('\n', ' ').replace('\r', ' ')[:150]
                                if body and body not in ["[removed]", "[deleted]"]:
                                    comment_strs.append(f"{author}: {body}...")
                            comments_text = " | ".join(comment_strs) if comment_strs else "No top comments found."
                        except Exception:
                            comments_text = "Failed to load comments."

                    md_post = f"### [{post.title}]({post.url})\n"
                    md_post += f"- **r/{post.subreddit}** | ⬆️ {post.score} | 💬 {post.num_comments} | 📅 {created_date}\n"
                    md_post += f"- [View on Reddit](https://www.reddit.com{post.permalink})\n"
                    if include_comments and comments_text != "N/A":
                        md_post += f"- **Top Comments:** {comments_text}\n"
                    md_post += "---"
                    markdown_results.append(md_post)
                    
                    csv_rows.append({
                        "Title": post.title,
                        "Subreddit": f"r/{post.subreddit}",
                        "Score": post.score,
                        "Total Comments": post.num_comments,
                        "Date": created_date,
                        "URL": f"https://www.reddit.com{post.permalink}",
                        "Top 3 Comments (Preview)": comments_text,
                        "Selftext": post.selftext[:500] if post.selftext else ""
                    })
                
                if not found_any:
                    st.info("🔍 No results found. Try broadening your topics, changing the time range, or enabling NSFW results if applicable.")
                    st.stop()
                
                # Save to Streamlit session state and update cooldown
                st.session_state['search_results'] = "\n\n".join(markdown_results)
                st.session_state['csv_data'] = csv_rows
                st.session_state['last_search_time'] = time.time()
                
            # SAFEGUARD 4: Graceful API Exception Handling
            except RedditAPIException as e:
                error_msg = str(e)
                if "RATELIMIT" in error_msg:
                    st.error("⏳ Reddit's API rate limit has been reached. Please wait a minute before trying again.")
                elif "UNAVAILABLE" in error_msg or "SERVICE" in error_msg:
                    st.error("🔧 Reddit's API is temporarily unavailable. Please try again later.")
                else:
                    st.error(f"❌ Reddit API Error: {error_msg}")
                st.stop()
                
            except Exception as e:
                st.error(f"❌ Unexpected error fetching data: {str(e)}. Check your Reddit API credentials in Secrets.")
                st.stop()

# --- Display Results ---
if 'search_results' in st.session_state:
    st.markdown("### 📊 Results Preview")
    st.markdown(st.session_state['search_results'])
    
    st.markdown("---")
    st.markdown("### 📥 Download Data")
    
    if 'csv_data' in st.session_state:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=st.session_state['csv_data'][0].keys())
        writer.writeheader()
        writer.writerows(st.session_state['csv_data'])
        
        st.download_button(
            label="⬇️ Download CSV",
            data=output.getvalue(),
            file_name="reddit_search_results.csv",
            mime="text/csv",
            use_container_width=True
        )
