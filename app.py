import os
import requests
import streamlit as st
import csv
import io
from datetime import datetime, timezone

# Page configuration
st.set_page_config(page_title="Reddit Thread Finder", page_icon="🔍", layout="wide")

st.title("🔍 Reddit Topic Thread Finder & Exporter")
st.markdown("Search intersecting Reddit discussions and export the results to CSV. *(Data is fetched live and not stored).*")

# Securely pull User-Agent from HF Space Secrets, with a safe fallback
USER_AGENT = os.getenv("REDDIT_USER_AGENT", "linux:reddit-topic-finder:v1.0 (by u/YourUsername)")

# --- Sidebar for Inputs ---
with st.sidebar:
    st.header("Search Parameters")
    main_topic = st.text_input("Main Topic *", placeholder="e.g., Machine Learning")
    
    st.subheader("Advanced Options")
    sec_topic1 = st.text_input("Secondary Topic 1 (Optional)", placeholder="e.g., Ethics")
    sec_topic2 = st.text_input("Secondary Topic 2 (Optional)", placeholder="e.g., Jobs")
    sec_topic3 = st.text_input("Secondary Topic 3 (Optional)", placeholder="e.g., Open Source")
    
    target_subreddit = st.text_input("Restrict to Subreddit (Optional)", placeholder="e.g., MachineLearning")
    include_comments = st.checkbox("Include Top 3 Comments (Slower)", value=False)
    
    sort_by = st.selectbox("Sort By", ["relevance", "top", "new", "comments"], index=0)
    time_filter = st.selectbox("Time Range", ["all", "year", "month", "week", "day"], index=1)
    limit = st.slider("Max Results", min_value=5, max_value=25, value=10, step=5)
    
    search_btn = st.button("🔍 Search & Generate CSV", type="primary", use_container_width=True)

# --- Main Search Logic ---
if search_btn or 'search_results' in st.session_state:
    if not main_topic or not main_topic.strip():
        st.warning("⚠️ Please enter at least a main topic.")
    else:
        with st.spinner("Searching Reddit..."):
            # Build boolean query
            q = f'"{main_topic.strip()}"'
            secondary_topics = [t.strip() for t in [sec_topic1, sec_topic2, sec_topic3] if t and t.strip()]
            if secondary_topics:
                parts = [f'"{t}"' for t in secondary_topics]
                q += f' AND ({" OR ".join(parts)})'
            
            # Subreddit scoping
            if target_subreddit and target_subreddit.strip():
                clean_sub = target_subreddit.strip().replace('r/', '')
                q = f"subreddit:{clean_sub} {q}"

            url = "https://www.reddit.com/search.json"
            headers = {"User-Agent": USER_AGENT}
            
            # Safety cap for comments
            safe_limit = 10 if include_comments else limit
            
            params = {
                "q": q,
                "sort": sort_by,
                "limit": safe_limit,
                "type": "link",
                "t": time_filter
            }
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                
                if response.status_code == 429:
                    st.error("⏳ Reddit is rate-limiting us. Please wait a minute and try again.")
                    st.stop()
                    
                response.raise_for_status()
                data = response.json()
                
                children = data.get("data", {}).get("children", [])
                if not children:
                    st.info("🔍 No results found. Try broadening your topics or changing the time range.")
                    st.stop()
                
                markdown_results = []
                csv_rows = []
                
                for child in children:
                    post = child["data"]
                    created_date = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).strftime('%Y-%m-%d')
                    post_url = f"https://www.reddit.com{post['permalink']}"
                    
                    comments_text = "N/A"
                    if include_comments:
                        try:
                            comment_url = f"https://www.reddit.com{post['permalink']}.json?limit=3&sort=top"
                            comment_resp = requests.get(comment_url, headers=headers, timeout=5)
                            if comment_resp.status_code == 200:
                                comment_data = comment_resp.json()
                                if len(comment_data) > 1:
                                    comment_children = comment_data[1].get("data", {}).get("children", [])
                                    top_comments = []
                                    for c in comment_children:
                                        c_data = c.get("data", {})
                                        body = c_data.get("body", "")
                                        author = c_data.get("author", "[deleted]")
                                        if body and body not in ["[removed]", "[deleted]"]:
                                            top_comments.append(f"{author}: {body[:150]}...")
                                        if len(top_comments) >= 3:
                                            break
                                    comments_text = " | ".join(top_comments) if top_comments else "No top comments found."
                        except Exception:
                            comments_text = "Failed to load comments."

                    md_post = f"### [{post['title']}]({post['url']})\n"
                    md_post += f"- **r/{post['subreddit']}** | ⬆️ {post['score']} | 💬 {post['num_comments']} | 📅 {created_date}\n"
                    md_post += f"- [View on Reddit]({post_url})\n"
                    if include_comments and comments_text != "N/A":
                        md_post += f"- **Top Comments:** {comments_text}\n"
                    md_post += "---"
                    markdown_results.append(md_post)
                    
                    csv_rows.append({
                        "Title": post["title"],
                        "Subreddit": f"r/{post['subreddit']}",
                        "Score": post["score"],
                        "Total Comments": post["num_comments"],
                        "Date": created_date,
                        "URL": post_url,
                        "Top 3 Comments (Preview)": comments_text,
                        "Selftext": post.get("selftext", "")[:500]
                    })
                
                # Save to Streamlit session state (persists across reruns)
                st.session_state['search_results'] = "\n\n".join(markdown_results)
                st.session_state['csv_data'] = csv_rows
                
            except Exception as e:
                st.error(f"❌ Error fetching data: {str(e)}.")
                st.stop()

# --- Display Results ---
if 'search_results' in st.session_state:
    st.markdown("### 📊 Results Preview")
    st.markdown(st.session_state['search_results'])
    
    st.markdown("---")
    st.markdown("### 📥 Download Data")
    
    if 'csv_data' in st.session_state:
        # Generate CSV entirely in memory (no temporary files needed!)
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
