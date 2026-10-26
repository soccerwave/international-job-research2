// Read-only EURAXESS country-card diagnostic for Cloudflare Workers.
// On demand only. Does not store, proxy, or expose downloaded HTML.
const HOST = "https://euraxess.ec.europa.eu";
const SEARCH = HOST + "/jobs/search";
const COUNTRY = "job_country:794";
const OFFER = "offer_type:job_offer";
function cards(html) {
  const fragments = html.split(/<div\\b[^>]*\\bid=["']job-teaser-content["'][^>]*>/i).slice(1);
  return fragments.map(fragment => {
    const chunk = fragment.split(/<\\/div>/i).slice(0,12).join("</div>");
    const id = chunk.match(/href=["'](?:https?:\\/\\/euraxess\\.ec\\.europa\\.eu)?\\/jobs\\/(\\d+)/i)?.[1];
    const labels = [...chunk.matchAll(/<[^>]*class=["'][^"']*ecl-label[^"']*["'][^>]*>([\\s\\S]*?)<\\/[^>]+>/gi)]
      .map(m => m[1].replace(/<[^>]*>/g,"").trim());
    return id ? {id, labels:labels.slice(0,3)} : null;
  }).filter(Boolean);
}
async function inspect(label,url) {
  const response = await fetch(url,{signal:AbortSignal.timeout(12000),redirect:"follow"});
  const html = await response.text();
  const rows = cards(html);
  return {label,status:response.status,finalUrl:response.url,rows,
    uniqueIds:[...new Set(rows.map(x=>x.id))],
    htmlBytes:html.length,
    countrySelected:/<option\\b(?=[^>]*value=["']794["'])(?=[^>]*selected)[^>]*>/i.test(html),
    offerSelected:/<option\\b(?=[^>]*value=["']job_offer["'])(?=[^>]*selected)[^>]*>/i.test(html)};
}
export default {
  async fetch() {
    try {
      const url = new URL(SEARCH);
      url.searchParams.set("f[0]",COUNTRY);
      url.searchParams.set("f[1]",OFFER);
      const first = await inspect("germany_page_0",url.toString());
      const next = new URL(url); next.searchParams.set("page","1");
      const second = await inspect("germany_page_1",next.toString());
      const all = [...first.rows,...second.rows];
      const countryLabels = all.map(x=>({id:x.id,country:x.labels[1]??null,offer:x.labels[0]??null}));
      return Response.json({
        tests:{bothHttp200:first.status===200&&second.status===200,
          filtersMarkedSelected:first.countrySelected&&first.offerSelected,
          pageHasNewIds:second.uniqueIds.some(x=>!first.uniqueIds.includes(x)),
          allCardsCountryGermany:countryLabels.length>0&&countryLabels.every(x=>x.country==="Germany"),
          allCardsJob:countryLabels.length>0&&countryLabels.every(x=>x.offer==="JOB")},
        count:{page0:first.uniqueIds.length,page1:second.uniqueIds.length},
        cards:countryLabels.slice(0,25),
        warning:"A false result may indicate a page markup change. Do not publish raw HTML or credentials."
      });
    } catch(e) {return Response.json({errorType:e.name,message:String(e.message).slice(0,180)},{status:200});}
  }
};
