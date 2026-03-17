import os
import time
import resend
from dotenv import load_dotenv
from supabase import create_client, Client
load_dotenv()
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Load variables from .env

resend.api_key = os.getenv("RESEND_API_KEY")

current_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(current_dir, "static", "March17Pulse.png")

def get_subscribers():
    try:
        # SELECT email FROM subscribers
        response = supabase.table("subscribers").select("email").execute()
         
        # Flatten the list of dictionaries [{'email': '...'}, ...] into ['...', '...']
        email_list = [row['email'] for row in response.data]
        return email_list
    except Exception as e:
        print(f"❌ Database error: {e}")
        return []

def send_newsletter():
    subject = "Strategic Pulse: Day 17 of Iran War"
    
    # 1. Read the image file as bytes
    try:
        with open(image_path, "rb") as f:
            image_data = list(f.read()) # Resend Python SDK expects a list of bytes
    except FileNotFoundError:
        print(f"❌ Error: Image not found at {image_path}")
        return

    # Your HTML content (keep your existing HTML, just ensuring the CID matches)
    html_content = """
    <div dir="ltr">
    <div>Dear reader,</div>
    <div><br /></div>
    <div>
        The conflict enters its third week with a sharpening divide between political rhetoric and reality. While the Trump
        administration implies a unilateral timeline for resolution, Tehran’s leverage over the Strait of Hormuz remains the
        primary variable. Unlike previous theatres (e.g., Venezuela), Iran’s ability to choke 20% of global oil flow creates
        a dynamic where the market, not the White House, dictates terms (TACO) of ending the war. Our new Escalation Score
        metric is at 0.24, showing the war is not de-escalating currently. From a financial perspective, nothing indicates
        alleviating market stress. Instead the longer this drags on the larger the impact on global growth (implying further
        discounts to markets). Commodities will be able to find their way to markets eventually but this is a long
        process.  
    </div>
    <div style="text-align: left; margin: 20px 0;">
        <img src="cid:pulse-chart" alt="Escalation Score" width="545" height="158" />
    </div>
    <div>
        We have updated our <b>Strategic Escalation Score</b> to integrate physical strikes with market stress and naval
        activity in Hormuz. Despite a reduction, albeit at glacier speed, strikes originating from Iran the index remains in
        the red due to two critical factors:
    </div>
    <div><br /></div>
    <div>
        · <b>Shipping</b>: Commercial transits have effectively bottomed out, yet Iranian oil sales remain at pre-war
        levels. Iran is successfully funding its operations in real-time while the rest of the world bears the cost of the
        blockade. The latest ship we tracking passing through was “KING CHAIN”, sailing under the flag of Cameroon and
        previously shipping under name of “STELLANN” and others is officially sanctioned (imo: 9277761) under various
        jurisdictions. Most ships are, although a few are not. SHIVALIK crossed to sail to India and is not part of the
        shadow fleet. This seemed to be negotiated between Iran and India, showing diplomacy can get ships through.
    </div>
    <div><br /></div>
    <div>
        · <b>The Mine-Sweeping Deficit</b>: Reports (via TWZ &amp; Defense Security Asia) indicate that legacy U.S.
        mine-sweepers were decommissioned last year. Their replacements (LCS units like the USS Tulsa) were recently spotted
        in Malaysia rather than the Gulf. This asset gap implies that a quick reopening of the Strait is physically
        impossible, regardless of political statements.
    </div>
    <div><br /></div>
    <b>The Data Brief:</b><br />· <b>Kinetics</b>: Strike frequency is slowing, but lethality remains high.<br />·
    <b>Maritime</b>: Shipping through Hormuz is virtually non-existent for third-party vessels.<br />· <b>Markets</b>:
    Crude spreads and the Baltic Dry Clean Tanker Index (BDTI) are implying a &quot;higher for longer&quot; inflation
    regime, with Europe markets impacted a lot but troubles also brewing in Asia (e.g. India). <br />
    <div>
        · <b>Casualties</b>: Our T-1 time-series shows a steady climb. While &quot;truth is the first casualty of war&quot;
        (so look at the trend, not absolutes) our aggregated quality sources indicate the human cost is beginning to outpace
        early-war projections.
    </div>
    <div><br /></div>
    <div>
        <font size="2"
        ><u><b>The Bottom Line</b>: </u></font
        >
    </div>
    <div>
        <font size="2"
        ><u
            >Expect a sustained negative financial impact. The potency of Iran’s disruption ensures this remains a global
            economic event rather than a localized skirmish. Inflationary pressures will continue to build the longer Hormuz
            remains closed and could be exacerbated if Iran successfully targets Middle Eastern supplies and refining.</u
        ></font
        >
    </div>
    <div><br /></div>
    <div>Feedback is much appreciated!</div>
    ———————————————————————————-<br />
    <div></div>
    <div><font size="1">Newsletter is send intermittently, not daily. </font></div>
    <font size="1">To unsubscribe, please reply to this email with &quot;UNSUBSCRIBE&quot;.</font
    ><br />———————————————————————————-<br /><br />
    </div>
    """

    subscribers = ["stan@warescalation.com"]
    #subscribers = get_subscribers()
    print(subscribers)
    for email in subscribers:
        try:
            resend.Emails.send({
                "from": "Stan <stan@warescalation.com>",
                "to": email,
                "subject": subject,
                "html": html_content,
                "attachments": [
                    {
                        "filename": "March17Pulse.png",
                        "content": image_data,  # FIX: Use 'content' (bytes) instead of 'path'
                        "content_id": "pulse-chart" 
                    }
                ]
            })
            print(f"✅ Sent to {email}")
            time.sleep(1) 
        except Exception as e:
            print(f"❌ Error sending to {email}: {e}")

if __name__ == "__main__":
    send_newsletter()