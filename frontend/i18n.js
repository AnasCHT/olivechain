/* OliveChain shared i18n: EN / FR / AR with RTL support.
   Pages call OC.t("key") at render time; switching language reloads the page
   so every dynamic render picks up the new dictionary. */
(function(){
  const D = {

  /* ---------------- shared ---------------- */
  "s.verified":      {en:"Ledger verified", fr:"Registre vérifié", ar:"تم التحقق من السجل"},
  "s.vfail":         {en:"Verification failed", fr:"Échec de la vérification", ar:"فشل التحقق"},
  "s.scans":         {en:"{n} consumer scans", fr:"{n} scans consommateurs", ar:"{n} عمليات مسح"},
  "s.myscan":        {en:"Your scan is now on the ledger", fr:"Votre scan est désormais inscrit au registre", ar:"تم تسجيل مسحك في السجل الآن"},
  "s.api":           {en:"API", fr:"API", ar:"API"},

  /* ---------------- bottle labels (/labels) ---------------- */
  "l.tag":       {en:"Label sheets", fr:"Planches d'étiquettes", ar:"صفحات الملصقات"},
  "l.n12":       {en:"12 per A4 — large (jars, boxes)", fr:"12 par A4 — grand (bocaux, cartons)", ar:"12 لكل A4 — كبير (جِرار، صناديق)"},
  "l.n24":       {en:"24 per A4 — standard bottle", fr:"24 par A4 — bouteille standard", ar:"24 لكل A4 — زجاجة قياسية"},
  "l.back":      {en:"← Dashboard", fr:"← Tableau de bord", ar:"→ لوحة المتابعة"},
  "l.print":     {en:"Print sheet", fr:"Imprimer la planche", ar:"اطبع الصفحة"},
  "l.note":      {en:"Each label's QR deep-links to the mobile verifier with this batch pre-filled. Print at 100% scale (no \"fit to page\") so physical sizes are exact. SVG codes stay crisp at any size.",
                  fr:"Le QR de chaque étiquette ouvre le vérificateur mobile avec ce lot pré-rempli. Imprimez à 100 % (sans « ajuster à la page ») pour des tailles exactes. Les QR en SVG restent nets à toute taille.",
                  ar:"رمز QR في كل ملصق يفتح أداة التحقق على الجوال مع تعبئة هذه الدفعة مسبقًا. اطبع بمقياس 100٪ (دون «ملاءمة الصفحة») لتكون الأحجام دقيقة. رموز SVG تبقى واضحة بأي حجم."},
  "l.lsub":      {en:"Verified origin & circularity", fr:"Origine & circularité vérifiées", ar:"أصل ودائرية موثّقان"},
  "l.lhint":     {en:"Scan to see this oil's full signed history", fr:"Scannez pour voir tout l'historique signé de cette huile", ar:"امسح لرؤية كامل السجل الموقَّع لهذا الزيت"},
  "l.err":       {en:"Unknown batch — no labels to print. Check the batch id.", fr:"Lot inconnu — aucune étiquette à imprimer. Vérifiez le code du lot.", ar:"دفعة غير معروفة — لا ملصقات للطباعة. تحقّق من رمز الدفعة."},

  /* ---------------- customer (/verify) ---------------- */
  "c.tag":       {en:"Verify your bottle", fr:"Vérifiez votre bouteille", ar:"تحقّق من زجاجتك"},
  "c.nav.how":   {en:"How it works", fr:"Comment ça marche", ar:"كيف يعمل"},
  "c.nav.see":   {en:"What you'll see", fr:"Ce que vous verrez", ar:"ماذا سترى"},
  "c.eyebrow":   {en:"Every bottle has a story on record", fr:"Chaque bouteille a une histoire enregistrée", ar:"لكل زجاجة قصة موثّقة"},
  "c.h1":        {en:"Is your olive oil what the label claims?", fr:"Votre huile d'olive est-elle conforme à son étiquette ?", ar:"هل زيت الزيتون لديك مطابق لما يدّعيه الملصق؟"},
  "c.lead":      {en:"Enter the batch code printed on your bottle. We re-verify its entire signed history — grove, mill, laboratory, bottling — the moment you ask, and show you what happened to every kilogram of by-product too.",
                  fr:"Saisissez le code de lot imprimé sur votre bouteille. Tout son historique signé — verger, moulin, laboratoire, embouteillage — est revérifié à l'instant même, et nous vous montrons aussi ce qu'est devenu chaque kilogramme de sous-produit.",
                  ar:"أدخل رمز الدفعة المطبوع على زجاجتك. نعيد التحقق من كامل سجلّها الموقّع — من البستان إلى المعصرة والمختبر والتعبئة — لحظة طلبك، ونُريك أيضًا ما حدث لكل كيلوغرام من المخلّفات."},
  "c.batchlabel":{en:"Batch code", fr:"Code de lot", ar:"رمز الدفعة"},
  "c.verify":    {en:"Verify my bottle", fr:"Vérifier ma bouteille", ar:"تحقّق من زجاجتي"},
  "c.verifying": {en:"Verifying…", fr:"Vérification…", ar:"جارٍ التحقق…"},
  "c.err.empty": {en:"Please enter the batch code from your bottle.", fr:"Veuillez saisir le code de lot de votre bouteille.", ar:"الرجاء إدخال رمز الدفعة من زجاجتك."},
  "c.err.notfound":{en:"We couldn't find that batch. Check the code on the label — e.g. BATCH-2025-001.",
                  fr:"Lot introuvable. Vérifiez le code sur l'étiquette — p. ex. BATCH-2025-001.",
                  ar:"لم نعثر على هذه الدفعة. تحقّق من الرمز على الملصق — مثل BATCH-2025-001."},
  "c.demo":      {en:"No bottle at hand? Try a bottle from the current pilot:", fr:"Pas de bouteille sous la main ? Essayez un lot du pilote en cours :", ar:"لا زجاجة بين يديك؟ جرّب دفعة من التجربة الحالية:"},
  "c.qrnote":    {en:"The QR code on the bottle label points to this page with the code pre-filled.",
                  fr:"Le code QR de l'étiquette mène à cette page avec le code déjà rempli.",
                  ar:"رمز QR على ملصق الزجاجة يقود إلى هذه الصفحة مع الرمز معبأً مسبقًا."},
  "c.strip.chain":{en:"Chain integrity, live", fr:"Intégrité de la chaîne, en direct", ar:"سلامة السلسلة، مباشرة"},
  "c.strip.ok":  {en:"✓ Verified", fr:"✓ Vérifiée", ar:"✓ موثوقة"},
  "c.strip.bad": {en:"✕ Failed", fr:"✕ Échec", ar:"✕ فشل"},
  "c.strip.records":{en:"Signed records", fr:"Enregistrements signés", ar:"سجلات موقّعة"},
  "c.strip.orgs":{en:"Named organizations", fr:"Organisations identifiées", ar:"منظمات معرَّفة"},
  "c.strip.scans":{en:"Consumer scans", fr:"Scans consommateurs", ar:"عمليات مسح المستهلكين"},
  "c.how.h":     {en:"How verification works", fr:"Comment fonctionne la vérification", ar:"كيف يعمل التحقق"},
  "c.how.lede":  {en:"This is not a marketing badge. Your request triggers a live audit of the cryptographic record behind this exact batch.",
                  fr:"Ce n'est pas un badge marketing. Votre demande déclenche un audit en direct de l'enregistrement cryptographique de ce lot précis.",
                  ar:"هذه ليست شارة تسويقية. طلبك يُطلق تدقيقًا مباشرًا للسجل المشفَّر لهذه الدفعة بعينها."},
  "c.how.1h":    {en:"You enter the code", fr:"Vous saisissez le code", ar:"تُدخل الرمز"},
  "c.how.1p":    {en:"Each bottle points to the batch it was filled from. The batch — not the bottle — is the unit of truth, so every record concerns oil that was actually pressed together.",
                  fr:"Chaque bouteille renvoie au lot dont elle provient. Le lot — pas la bouteille — est l'unité de vérité : chaque enregistrement concerne de l'huile réellement pressée ensemble.",
                  ar:"كل زجاجة تشير إلى الدفعة التي عُبّئت منها. الدفعة — لا الزجاجة — هي وحدة الحقيقة، فكل سجل يخص زيتًا عُصر معًا فعلًا."},
  "c.how.2h":    {en:"The chain is re-checked", fr:"La chaîne est revérifiée", ar:"يُعاد فحص السلسلة"},
  "c.how.2p":    {en:"Every event in the batch's history is hash-linked to the one before it and signed by the organization that performed it. All of it is re-verified at the moment you ask — nothing is cached.",
                  fr:"Chaque événement de l'historique est chaîné par empreinte au précédent et signé par l'organisation qui l'a réalisé. Tout est revérifié au moment de votre demande — rien n'est mis en cache.",
                  ar:"كل حدث في تاريخ الدفعة مرتبط ببصمة الحدث السابق وموقَّع من المنظمة التي نفّذته. يُعاد التحقق من كل ذلك لحظة طلبك — لا شيء مخزَّن مسبقًا."},
  "c.how.3h":    {en:"Your scan joins the record", fr:"Votre scan rejoint le registre", ar:"مسحك ينضم إلى السجل"},
  "c.how.3p":    {en:"Your verification is itself written to the ledger as a signed event. You become part of the batch's history, and the producers see that consumers are checking.",
                  fr:"Votre vérification est elle-même inscrite au registre comme événement signé. Vous entrez dans l'histoire du lot, et les producteurs voient que les consommateurs vérifient.",
                  ar:"تحقُّقك نفسه يُكتب في السجل كحدث موقَّع. تصبح جزءًا من تاريخ الدفعة، ويرى المنتجون أن المستهلكين يتحققون."},
  "c.see.h":     {en:"What you'll see", fr:"Ce que vous verrez", ar:"ماذا سترى"},
  "c.see.lede":  {en:"Plain-language evidence — no blockchain jargon without context.", fr:"Des preuves en langage clair — pas de jargon blockchain hors contexte.", ar:"أدلة بلغة واضحة — دون مصطلحات تقنية بلا سياق."},
  "c.see.1h":    {en:"The journey", fr:"Le parcours", ar:"الرحلة"},
  "c.see.1p":    {en:"Grove, harvest, transport, cold-press milling, independent laboratory results, bottling and shipment — each step signed and dated, corrections shown honestly.",
                  fr:"Verger, récolte, transport, extraction à froid, résultats d'un laboratoire indépendant, embouteillage et expédition — chaque étape signée et datée, corrections affichées honnêtement.",
                  ar:"البستان، الحصاد، النقل، العصر على البارد، نتائج مختبر مستقل، التعبئة والشحن — كل خطوة موقَّعة ومؤرَّخة، والتصحيحات معروضة بصدق."},
  "c.see.2h":    {en:"The by-products", fr:"Les sous-produits", ar:"المخلّفات"},
  "c.see.2p":    {en:"Pressing leaves pomace and leaves. See how many kilograms were recovered into compost, polyphenols and bioenergy — reconciled by mass balance, not by promise.",
                  fr:"Le pressage laisse grignons et feuilles. Voyez combien de kilogrammes ont été valorisés en compost, polyphénols et bioénergie — réconciliés par bilan de masse, pas sur promesse.",
                  ar:"يخلّف العصر الثفل وأوراق الزيتون. شاهد كم كيلوغرامًا استُرجع سمادًا وبوليفينولات وطاقة حيوية — بموازنة كتلية موثّقة لا بوعود."},
  "c.see.3h":    {en:"The recognition", fr:"La reconnaissance", ar:"التقدير"},
  "c.see.3p":    {en:"Which cooperatives, mills and recyclers earned EcoPoints — non-transferable credits granted only for actions the system could independently verify.",
                  fr:"Quelles coopératives, moulins et recycleurs ont gagné des ÉcoPoints — des crédits non transférables, accordés uniquement pour des actions vérifiables.",
                  ar:"أي التعاونيات والمعاصر وجهات التدوير كسبت نقاطًا بيئية — أرصدة غير قابلة للتحويل تُمنح فقط لأفعال تحقق منها النظام باستقلالية."},
  "c.promise.h": {en:"Our promise about honesty", fr:"Notre promesse d'honnêteté", ar:"وعدنا بالصدق"},
  "c.promise.p": {en:"<b>A ledger cannot taste oil.</b> Physical truth still requires scales, laboratories, identity controls and audits. What this system guarantees is different and precise: every claim you see was signed by a named organization, nothing was silently altered afterwards, suspicious data is flagged for review rather than hidden, and rewards were only issued where quantities reconcile. When verification fails, the passport says so — <b>plainly</b>.",
                  fr:"<b>Un registre ne peut pas goûter l'huile.</b> La vérité physique exige toujours balances, laboratoires, contrôles d'identité et audits. Ce que ce système garantit est différent et précis : chaque affirmation a été signée par une organisation identifiée, rien n'a été modifié en silence, les données suspectes sont signalées plutôt que cachées, et les récompenses ne sont émises que lorsque les quantités concordent. Quand la vérification échoue, le passeport le dit — <b>clairement</b>.",
                  ar:"<b>السجل لا يستطيع تذوّق الزيت.</b> فالحقيقة المادية ما زالت تتطلب موازين ومختبرات وضوابط هوية وتدقيقًا. ما يضمنه هذا النظام مختلف ودقيق: كل ادعاء تراه وقّعته منظمة معرَّفة، ولا شيء عُدِّل بصمت، والبيانات المريبة تُعلَّم للمراجعة لا تُخفى، والمكافآت لا تُصرف إلا حيث تتطابق الكميات. وعندما يفشل التحقق، يقولها الجواز — <b>بوضوح</b>."},
  "c.foot":      {en:"OliveChain — verifiable circular trust for olive oil.", fr:"OliveChain — confiance circulaire vérifiable pour l'huile d'olive.", ar:"أوليف تشين — ثقة دائرية قابلة للتحقق لزيت الزيتون."},
  "c.foot.mobile":{en:"📱 Mobile app", fr:"📱 Appli mobile", ar:"📱 تطبيق الجوال"},
  "c.foot.dash": {en:"Consortium dashboard", fr:"Tableau de bord du consortium", ar:"لوحة متابعة الاتحاد"},

  /* ---------------- passport ---------------- */
  "p.back":      {en:"← Trust dashboard", fr:"← Tableau de bord", ar:"→ لوحة المتابعة"},
  "p.back2":     {en:"← Verify another bottle", fr:"← Vérifier une autre bouteille", ar:"→ تحقّق من زجاجة أخرى"},
  "p.eyebrow":   {en:"Verifiable circular olive-oil passport", fr:"Passeport circulaire vérifiable de l'huile d'olive", ar:"جواز دائري قابل للتحقق لزيت الزيتون"},
  "p.sub":       {en:"From the grove, and back to it.", fr:"Du verger, et retour au verger.", ar:"من البستان، وإليه يعود."},
  "p.journey.h": {en:"The journey of this oil", fr:"Le parcours de cette huile", ar:"رحلة هذا الزيت"},
  "p.journey.lede":{en:"Every step below was recorded by the organization that performed it and digitally signed. Records can be corrected, but never silently changed — corrections are shown.",
                  fr:"Chaque étape ci-dessous a été enregistrée par l'organisation qui l'a réalisée et signée numériquement. Les enregistrements peuvent être corrigés, jamais modifiés en silence — les corrections sont affichées.",
                  ar:"كل خطوة أدناه سجّلتها المنظمة التي نفّذتها ووقّعتها رقميًا. يمكن تصحيح السجلات لكن لا تُغيَّر بصمت أبدًا — والتصحيحات معروضة."},
  "p.byword":    {en:"by", fr:"par", ar:"بواسطة"},
  "p.signed":    {en:"digitally signed", fr:"signé numériquement", ar:"موقَّع رقميًا"},
  "p.corr":      {en:"A signed correction was applied to this record; the original remains on file.",
                  fr:"Une correction signée a été appliquée à cet enregistrement ; l'original reste archivé.",
                  ar:"طُبّق تصحيح موقَّع على هذا السجل؛ ويبقى الأصل محفوظًا."},
  "p.evid.ok":   {en:"✓ evidence intact", fr:"✓ preuve intacte", ar:"✓ الدليل سليم"},
  "p.evid.bad":  {en:"✕ evidence altered", fr:"✕ preuve altérée", ar:"✕ الدليل معدَّل"},
  "p.byp.h":     {en:"What happened to the by-products", fr:"Ce que sont devenus les sous-produits", ar:"ما الذي حدث للمخلّفات"},
  "p.byp.lede":  {en:"Pressing olives leaves pomace, leaves and stones. This batch's residues were weighed, tracked to a recovery partner, and turned into new resources — verified by mass balance, not by promise.",
                  fr:"Le pressage laisse grignons, feuilles et noyaux. Les résidus de ce lot ont été pesés, suivis jusqu'à un partenaire de valorisation, et transformés en nouvelles ressources — vérifié par bilan de masse, pas sur promesse.",
                  ar:"يخلّف عصر الزيتون الثفل والأوراق والنوى. وقد وُزنت مخلّفات هذه الدفعة وتُتبّعت حتى شريك الاسترجاع وحُوّلت إلى موارد جديدة — بتحقق الموازنة الكتلية لا بالوعود."},
  "p.ring":      {en:"recovered", fr:"valorisé", ar:"استُرجع"},
  "p.accounted": {en:"{kg} kg of {type}, accounted for", fr:"{kg} kg de {type}, comptabilisés", ar:"{kg} كغ من {type}، محسوبة بالكامل"},
  "p.ringp":     {en:"Weighed at the mill, transferred under custody records, and converted by a verified recovery partner. The quantities created, transported, accepted and transformed reconcile.",
                  fr:"Pesé au moulin, transféré sous traçabilité, converti par un partenaire de valorisation vérifié. Les quantités créées, transportées, acceptées et transformées concordent.",
                  ar:"وُزن في المعصرة، ونُقل بسجلات عهدة، وحوّله شريك استرجاع موثّق. الكميات المنتَجة والمنقولة والمقبولة والمحوَّلة متطابقة."},
  "p.rrow.ok":   {en:"✓ recovery verified", fr:"✓ valorisation vérifiée", ar:"✓ استرجاع موثّق"},
  "p.rrow.wait": {en:"⏳ recovery in progress", fr:"⏳ valorisation en cours", ar:"⏳ استرجاع قيد الإنجاز"},
  "p.rec.h":     {en:"Who earned recognition", fr:"Qui a été récompensé", ar:"من نال التقدير"},
  "p.rec.lede":  {en:"EcoPoints are non-transferable credits issued only for actions the system could verify.",
                  fr:"Les ÉcoPoints sont des crédits non transférables, émis uniquement pour des actions vérifiables.",
                  ar:"النقاط البيئية أرصدة غير قابلة للتحويل تُصرف فقط لأفعال تحقق منها النظام."},
  "p.footok":    {en:"Every record above sits on an append-only, hash-chained ledger. The full chain and all signatures were re-verified live when this passport was requested.",
                  fr:"Chaque enregistrement repose sur un registre chaîné en ajout seul. La chaîne complète et toutes les signatures ont été revérifiées en direct à l'ouverture de ce passeport.",
                  ar:"كل سجل أعلاه محفوظ في سجل مسلسل بالإلحاق فقط. أُعيد التحقق من كامل السلسلة وكل التواقيع مباشرة عند طلب هذا الجواز."},
  "p.footwarn":  {en:"Warning: ledger verification failed — ", fr:"Attention : échec de la vérification du registre — ", ar:"تحذير: فشل التحقق من السجل — "},
  "p.footfixed": {en:"Physical truth still requires scales, laboratories, identity controls, audits and governance — this record coordinates that evidence and makes later alteration detectable.",
                  fr:"La vérité physique exige toujours balances, laboratoires, contrôles d'identité, audits et gouvernance — ce registre coordonne ces preuves et rend toute altération ultérieure détectable.",
                  ar:"الحقيقة المادية ما زالت تتطلب موازين ومختبرات وضوابط هوية وتدقيقًا وحوكمة — هذا السجل ينسّق تلك الأدلة ويجعل أي تعديل لاحق قابلًا للاكتشاف."},
  "p.batchword": {en:"batch", fr:"lot", ar:"دفعة"},
  "p.print":     {en:"Print passport", fr:"Imprimer le passeport", ar:"اطبع الجواز"},
  "p.pdf":       {en:"Signed PDF", fr:"PDF signé", ar:"PDF موقَّع"},
  "p.vc":        {en:"Verifiable Credential (JSON-LD)", fr:"Attestation vérifiable (JSON-LD)", ar:"شهادة قابلة للتحقق (JSON-LD)"},
  "p.err":       {en:"Could not load passport for this batch — is the batch id correct and the server running?",
                  fr:"Impossible de charger le passeport de ce lot — le code est-il correct et le serveur actif ?",
                  ar:"تعذّر تحميل جواز هذه الدفعة — هل الرمز صحيح والخادم يعمل؟"},

  /* stage labels (keyed by API's English label) */
  "p.st.Grown":            {en:"Grown", fr:"Cultivé", ar:"زُرع"},
  "p.st.Harvested":        {en:"Harvested", fr:"Récolté", ar:"حُصد"},
  "p.st.Collected":        {en:"Collected", fr:"Collecté", ar:"جُمع"},
  "p.st.Milled":           {en:"Milled", fr:"Pressé", ar:"عُصر"},
  "p.st.Quality verified": {en:"Quality verified", fr:"Qualité vérifiée", ar:"جودة موثّقة"},
  "p.st.Bottled":          {en:"Bottled", fr:"Embouteillé", ar:"عُبّئ"},
  "p.st.Shipped to market":{en:"Shipped to market", fr:"Expédié au marché", ar:"شُحن إلى السوق"},

  /* fact labels */
  "p.f.cultivar":{en:"Cultivar", fr:"Cultivar", ar:"الصنف"},
  "p.f.plot":    {en:"Plot", fr:"Parcelle", ar:"القطعة"},
  "p.f.practices":{en:"Practices", fr:"Pratiques", ar:"الممارسات"},
  "p.f.date":    {en:"Date", fr:"Date", ar:"التاريخ"},
  "p.f.quantity":{en:"Quantity", fr:"Quantité", ar:"الكمية"},
  "p.f.method":  {en:"Method", fr:"Méthode", ar:"الطريقة"},
  "p.f.weight":  {en:"Weight", fr:"Poids", ar:"الوزن"},
  "p.f.containers":{en:"Containers", fr:"Conteneurs", ar:"الحاويات"},
  "p.f.received":{en:"Olives received", fr:"Olives reçues", ar:"الزيتون المستلم"},
  "p.f.oil":     {en:"Oil produced", fr:"Huile produite", ar:"الزيت المنتَج"},
  "p.f.temp":    {en:"Temp", fr:"Temp.", ar:"الحرارة"},
  "p.f.class":   {en:"Class", fr:"Classe", ar:"الفئة"},
  "p.f.acidity": {en:"Free acidity", fr:"Acidité libre", ar:"الحموضة الحرة"},
  "p.f.defects": {en:"Defects", fr:"Défauts", ar:"العيوب"},
  "p.f.bottles": {en:"Bottles", fr:"Bouteilles", ar:"الزجاجات"},
  "p.f.filled":  {en:"Filled", fr:"Rempli le", ar:"تاريخ التعبئة"},
  "p.f.claims":  {en:"Claims", fr:"Mentions", ar:"الادعاءات"},
  "p.f.destination":{en:"Destination", fr:"Destination", ar:"الوجهة"},

  /* recovered output labels */
  "p.out.compost_kg":   {en:"kg compost", fr:"kg de compost", ar:"كغ سماد"},
  "p.out.polyphenols_g":{en:"g polyphenols", fr:"g de polyphénols", ar:"غ بوليفينولات"},
  "p.out.bioenergy_kwh":{en:"kWh bioenergy", fr:"kWh de bioénergie", ar:"ك.و.س طاقة حيوية"},
  "p.out.biochar_kg":   {en:"kg biochar", fr:"kg de biochar", ar:"كغ فحم حيوي"},
  "p.out.fertilizer_kg":{en:"kg fertilizer", fr:"kg d'engrais", ar:"كغ أسمدة"},
  "p.out.feedstock_kg": {en:"kg feedstock", fr:"kg de matière première", ar:"كغ مواد أولية"},
  "p.out.adsorbent_kg": {en:"kg adsorbent", fr:"kg d'adsorbant", ar:"كغ مواد ممتزة"},

  /* reward reasons */
  "p.why.residue_delivery":{en:"Delivered measured residues to an authorized processor", fr:"A livré des résidus mesurés à un valorisateur agréé", ar:"سلّم مخلّفات موزونة إلى معالج معتمد"},
  "p.why.quality_criteria":{en:"Met validated quality criteria", fr:"A satisfait aux critères de qualité validés", ar:"استوفى معايير الجودة المعتمدة"},
  "p.why.soil_return":     {en:"Returned recovered material to farmland", fr:"A restitué la matière valorisée aux terres agricoles", ar:"أعاد المواد المسترجعة إلى الأرض الزراعية"},
  "p.why.verified_recovery":{en:"Produced verified recovered material", fr:"A produit une matière valorisée vérifiée", ar:"أنتج موادَّ مسترجعة موثّقة"},
  "p.why.prompt_records":  {en:"Completed reliable records promptly", fr:"A complété des enregistrements fiables sans délai", ar:"أكمل سجلات موثوقة في حينها"},
  "p.why.circular_participation":{en:"Verified circular participation", fr:"Participation circulaire vérifiée", ar:"مشاركة دائرية موثّقة"},

  /* ---------------- mobile (/m) ---------------- */
  "m.tag":       {en:"Bottle verification", fr:"Vérification de bouteille", ar:"التحقق من الزجاجة"},
  "m.chain":     {en:"chain", fr:"chaîne", ar:"السلسلة"},
  "m.h1":        {en:"Check the truth behind your bottle.", fr:"Vérifiez la vérité derrière votre bouteille.", ar:"تحقّق من الحقيقة وراء زجاجتك."},
  "m.p":         {en:"Scan the label's QR code or type its batch code — the full signed history is re-verified live.",
                  fr:"Scannez le QR de l'étiquette ou saisissez le code de lot — tout l'historique signé est revérifié en direct.",
                  ar:"امسح رمز QR على الملصق أو اكتب رمز الدفعة — يُعاد التحقق من كامل السجل الموقَّع مباشرة."},
  "m.scanbtn":   {en:"Scan bottle QR", fr:"Scanner le QR", ar:"امسح رمز QR"},
  "m.or":        {en:"or enter the code", fr:"ou saisissez le code", ar:"أو أدخل الرمز"},
  "m.verify":    {en:"Verify", fr:"Vérifier", ar:"تحقّق"},
  "m.err.empty": {en:"Enter the batch code printed on the label.", fr:"Saisissez le code de lot imprimé sur l'étiquette.", ar:"أدخل رمز الدفعة المطبوع على الملصق."},
  "m.err.notfound":{en:"Batch not found — check the code on the label.", fr:"Lot introuvable — vérifiez le code sur l'étiquette.", ar:"الدفعة غير موجودة — تحقّق من الرمز على الملصق."},
  "m.err.https": {en:"Camera scanning needs a secure (HTTPS) connection — type the code instead.", fr:"Le scan caméra exige une connexion sécurisée (HTTPS) — saisissez le code.", ar:"مسح الكاميرا يتطلب اتصالًا آمنًا (HTTPS) — اكتب الرمز بدلًا من ذلك."},
  "m.err.nosupport":{en:"This browser can't scan QR codes — type the code instead.", fr:"Ce navigateur ne peut pas scanner les QR — saisissez le code.", ar:"هذا المتصفح لا يدعم مسح QR — اكتب الرمز بدلًا من ذلك."},
  "m.err.cam":   {en:"Camera unavailable or permission denied — type the code instead.", fr:"Caméra indisponible ou refusée — saisissez le code.", ar:"الكاميرا غير متاحة أو الرخصة مرفوضة — اكتب الرمز."},
  "m.chips":     {en:"No bottle at hand? Try a pilot batch:", fr:"Pas de bouteille ? Essayez un lot pilote :", ar:"لا زجاجة لديك؟ جرّب دفعة تجريبية:"},
  "m.hist.h":    {en:"Your scans", fr:"Vos scans", ar:"عمليات مسحك"},
  "m.hist.empty":{en:"Bottles you verify will appear here.", fr:"Les bouteilles vérifiées apparaîtront ici.", ar:"الزجاجات التي تتحقق منها ستظهر هنا."},
  "m.about.h":   {en:"What a scan really does", fr:"Ce que fait vraiment un scan", ar:"ما الذي يفعله المسح حقًا"},
  "m.about.1":   {en:"Every record behind a batch is digitally signed by the organization that made it and chained to the record before it. When you scan, the whole chain is re-checked on the spot — and your scan is written to the ledger as a signed event of its own.",
                  fr:"Chaque enregistrement d'un lot est signé numériquement par l'organisation qui l'a produit et chaîné au précédent. Quand vous scannez, toute la chaîne est revérifiée sur-le-champ — et votre scan est inscrit au registre comme événement signé.",
                  ar:"كل سجل خلف الدفعة موقَّع رقميًا من المنظمة التي أنشأته ومرتبط بالسجل السابق. عندما تمسح، يُعاد فحص السلسلة كلها فورًا — ويُكتب مسحك في السجل كحدث موقَّع بذاته."},
  "m.about.2":   {en:"A ledger cannot taste oil: laboratories, scales and audits provide the physical truth. This app makes any later alteration of their records detectable.",
                  fr:"Un registre ne peut pas goûter l'huile : laboratoires, balances et audits fournissent la vérité physique. Cette appli rend détectable toute altération ultérieure de leurs enregistrements.",
                  ar:"السجل لا يتذوق الزيت: المختبرات والموازين والتدقيق توفر الحقيقة المادية. هذا التطبيق يجعل أي تعديل لاحق لسجلاتها قابلًا للاكتشاف."},
  "m.scan.point":{en:"Point at the bottle's QR", fr:"Visez le QR de la bouteille", ar:"وجّه نحو رمز QR"},
  "m.scan.look": {en:"Looking for a code…", fr:"Recherche d'un code…", ar:"جارٍ البحث عن رمز…"},
  "m.scan.found":{en:"Found {code}", fr:"{code} trouvé", ar:"عُثر على {code}"},
  "m.spin":      {en:"Verifying the signed chain…", fr:"Vérification de la chaîne signée…", ar:"جارٍ التحقق من السلسلة الموقَّعة…"},
  "m.perr":      {en:"Could not load a passport for", fr:"Impossible de charger un passeport pour", ar:"تعذّر تحميل جواز لـ"},
  "m.perr2":     {en:"Check the code and try again.", fr:"Vérifiez le code et réessayez.", ar:"تحقّق من الرمز وحاول مجددًا."},
  "m.journey.lede":{en:"Tap a step to see its signed details.", fr:"Touchez une étape pour voir ses détails signés.", ar:"المس خطوة لعرض تفاصيلها الموقَّعة."},
  "m.byp.h":     {en:"The by-products", fr:"Les sous-produits", ar:"المخلّفات"},
  "m.byp.lede":  {en:"Verified by mass balance, not by promise.", fr:"Vérifié par bilan de masse, pas sur promesse.", ar:"موثّق بالموازنة الكتلية لا بالوعود."},
  "m.rec.h":     {en:"Recognition earned", fr:"Reconnaissance obtenue", ar:"التقدير المكتسب"},
  "m.rec.lede":  {en:"Non-transferable EcoPoints for verified actions only.", fr:"Des ÉcoPoints non transférables, pour actions vérifiées uniquement.", ar:"نقاط بيئية غير قابلة للتحويل لأفعال موثّقة فقط."},
  "m.footok":    {en:"The full hash chain and every signature were re-verified for this view.", fr:"La chaîne complète et chaque signature ont été revérifiées pour cet affichage.", ar:"أُعيد التحقق من كامل السلسلة وكل توقيع لهذا العرض."},
  "m.footwarn":  {en:"Warning: ", fr:"Attention : ", ar:"تحذير: "},
  "m.signedword":{en:"signed", fr:"signé", ar:"موقَّع"},
  "m.scansword": {en:"{n} scans", fr:"{n} scans", ar:"{n} مسحات"},
  "m.accounted": {en:"{kg} kg of {type}, accounted for", fr:"{kg} kg de {type}, comptabilisés", ar:"{kg} كغ من {type} محسوبة"},
  "m.ringp":     {en:"Weighed, transferred under custody records, and converted by a verified recovery partner.", fr:"Pesé, transféré sous traçabilité, converti par un partenaire vérifié.", ar:"وُزن ونُقل بسجلات عهدة وحوّله شريك استرجاع موثّق."},
  "m.rrow.ok":   {en:"✓ verified", fr:"✓ vérifié", ar:"✓ موثّق"},
  "m.rrow.wait": {en:"⏳ in progress", fr:"⏳ en cours", ar:"⏳ قيد الإنجاز"},
  };

  const LANGS = ["en", "fr", "ar"];
  let lang = localStorage.getItem("oc_lang") || "en";
  if (!LANGS.includes(lang)) lang = "en";

  function t(key, vars) {
    const e = D[key];
    let s = e ? (e[lang] || e.en) : key;
    if (vars) for (const k in vars) s = s.replace("{" + k + "}", vars[k]);
    return s;
  }

  function setLang(l) {
    if (!LANGS.includes(l)) return;
    localStorage.setItem("oc_lang", l);
    location.reload();
  }

  /* language switcher pills; pass a container element */
  function mountSwitcher(el) {
    el.innerHTML = LANGS.map(l =>
      `<button data-l="${l}" class="oc-lang${l === lang ? " on" : ""}">${l.toUpperCase()}</button>`).join("");
    el.querySelectorAll("button").forEach(b =>
      b.addEventListener("click", () => setLang(b.dataset.l)));
  }

  /* document-level direction, fonts, and shared RTL fixes */
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  const style = document.createElement("style");
  style.textContent = `
    .oc-lang{background:none;border:1px solid rgba(242,239,230,.35);color:inherit;cursor:pointer;
      font:600 10.5px 'Public Sans',sans-serif;padding:4px 8px;border-radius:3px;letter-spacing:.06em}
    .oc-lang.on{background:#c2a24b;border-color:#c2a24b;color:#1c2a21}
    .oc-langs{display:flex;gap:4px}
    html[lang="ar"] body{font-family:'Noto Naskh Arabic','Public Sans',sans-serif}
    html[lang="ar"] h1,html[lang="ar"] h2,html[lang="ar"] h3,html[lang="ar"] .lbrand{font-family:'Noto Naskh Arabic',serif}
    html[lang="ar"] .eyebrow,html[lang="ar"] .tag,html[lang="ar"] .lsub,html[lang="ar"] label,
    html[lang="ar"] .oc-lang{letter-spacing:0}
    html[dir="rtl"] .timeline{padding-left:0;padding-right:34px}
    html[dir="rtl"] .timeline::before{left:auto;right:11px}
    html[dir="rtl"] .stage::before{left:auto;right:-30px}
    html[dir="rtl"] .tbody{padding:0 39px 15px 15px}
  `;
  document.head.appendChild(style);
  if (lang === "ar" && !document.getElementById("oc-ar-font")) {
    const link = document.createElement("link");
    link.id = "oc-ar-font";
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;600;700&display=swap";
    document.head.appendChild(link);
  }

  window.OC = { t, lang, setLang, mountSwitcher };
})();
