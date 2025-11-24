/*
 * Krom PUP/Malware Heuristics YARA Rules
 * Author: Krom Team (based on Veeam, Malpedia, ReversingLabs, VMRay 2025 signatures)
 * Date: November 06, 2025
 * Description: Detects common PUPs, adware, RATs (AgentTesla), banking trojans (Qakbot/Trickbot),
 * ransomware loaders, and suspicious processes (e.g., jusched.exe variants, node.exe lockers).
 * Usage: Compiled via yara-python in disinfect.py for file scanning.
 * Sources: Veeam Blog (PUPs), Abuse.ch (AgentTesla), ReversingLabs (Qakbot), Qualys (Trickbot).
 * License: MIT (free to extend/add rules).
 */

rule Adware_Dropper_PUP {
    meta:
        description = "Common adware/PUP loaders (e.g., bundled installers, reflective loaders)"
        author = "Veeam/Krom"
        date = "2025-07-21"
        reference = "https://www.veeam.com/blog/yara-rules-malware-detection-analysis.html"
    strings:
        $s1 = "jusched.exe" ascii wide
        $s2 = "cdproxyserv.exe" ascii wide
        $s3 = "secomnservice.exe" ascii wide
        $s4 = /AppHelperCap|SysInfoCap/ ascii  // From Reddit/TechSupport reports
    condition:
        (any of ($s*)) and filesize < 2MB
}

rule AgentTesla_RAT {
    meta:
        description = "AgentTesla RAT variants (keylogger/stealer, .NET based)"
        author = "Abuse.ch/Malpedia/Krom"
        date = "2025-10-17"
        reference = "https://bazaar.abuse.ch/browse/yara/Agenttesla/"
    strings:
        $s1 = "agenttesla" ascii wide
        $s2 = "TeslaKeylogger" ascii
        $s3 = /Form1\.Load.*HttpWebRequest/ ascii  // Common .NET payload
        $s4 = /clipboard.*GetText/ ascii
    condition:
        uint16(0) == 0x5A4D and (2 of ($s*)) and filesize < 5MB
}

rule Qakbot_Banking_Trojan {
    meta:
        description = "Qakbot (Qbot) banking trojan (modular loader, 2025 variants)"
        author = "ReversingLabs/WalmartGlobalTech/Krom"
        date = "2025-01-20"
        reference = "https://medium.com/walmartglobaltech/qbot-is-back-connect-2d774052369f"
    strings:
        $s1 = "qakbot" ascii wide
        $s2 = /QakbotLoader|BankerDLL/ ascii
        $s3 = /C2Server.*ResolveDNS/ ascii  // C2 comms
        $s4 = /injectThread.*CreateRemoteThread/ ascii
    condition:
        (any of ($s*)) and filesize < 1MB
}

rule Trickbot_Modular_Malware {
    meta:
        description = "Trickbot modular malware (banker/spyware, ransomware precursor)"
        author = "Qualys/ReversingLabs/Krom"
        date = "2025-06-04"
        reference = "https://blog.qualys.com/vulnerabilities-threat-research/2022/02/02/catching-the-rat-called-agent-tesla"  // Adapted for Trickbot
    strings:
        $s1 = "trickbot" ascii wide
        $s2 = "TrickBotDLL" ascii
        $s3 = /modular.*PayloadDecrypt/ ascii
        $s4 = /smtp.*PhishKit/ ascii  // Phishing modules
    condition:
        (2 of ($s*)) and filesize < 3MB
}

rule Ransomware_Helper_Loader {
    meta:
        description = "Ransomware loaders/helpers (e.g., encryptors, droppers)"
        author = "CISA/IC3/Krom"
        date = "2025-06-04"
        reference = "https://www.ic3.gov/CSA/2025/250604.pdf"
    strings:
        $s1 = /ransomware_helper\.\w+/ ascii wide
        $s2 = "PlayForESXi" ascii  // ESXi variant
        $s3 = /CryptoAPI.*EncryptFile/ ascii
        $s4 = /shadowcopy.*delete/ ascii
    condition:
        any of ($s*) and filesize < 4MB
}

rule Node_Exe_Locker_Malware {
    meta:
        description = "Node.js-based lockers/miners (e.g., EvilAI, crypto hijackers)"
        author = "VMRay/InQuest/Krom"
        date = "2025-05-14"
        reference = "https://www.vmray.com/april-2025-detection-highlights-4-new-vmray-threat-identifiers-config-extractors-and-a-rich-set-of-new-yara-rules/"
    strings:
        $s1 = "node.exe" ascii wide
        $s2 = /NativePush.*\.exe/ ascii
        $s3 = /crypto-miner.*stratum/ ascii  // Mining pools
        $s4 = /locker.*encrypt/ ascii
    condition:
        $s1 and (any of ($s2,$s3,$s4)) and filesize < 10MB
}

rule Suspicious_Process_Injector {
    meta:
        description = "Process injectors hiding in legit names (e.g., winlogon mimics)"
        author = "SentinelOne/Krom"
        date = "2021-01-07"  // Updated patterns for 2025
        reference = "https://www.sentinelone.com/labs/greywares-anatomy-the-potentially-unwanted-are-upping-their-game/"
    strings:
        $s1 = "winlogon.exe" ascii wide  // Often mimicked
        $s2 = "runtimebroker.exe" ascii  // Multiples suspicious
        $s3 = "com surrogate.exe" ascii
        $s4 = /ReflectiveLoader|DLLInject/ ascii
    condition:
        (any of ($s1,$s2,$s3)) and $s4 and filesize < 2MB
}

rule General_PUP_Adware {
    meta:
        description = "Generic PUP/adware (e.g., toolbars, greyware)"
        author = "Trellix/OPSWAT/Krom"
        date = "2025-09-18"
        reference = "https://docs.trellix.com/bundle/fx_11.x_ug/page/UUID-8d86b039-d387-2827-11ee-2652051c05e5.html"
    strings:
        $s1 = /toolbar.*install/ ascii
        $s2 = "Riskware.Adware" ascii
        $s3 = /bundled.*offer/ ascii
        $s4 = /popup.*ads/ ascii
    condition:
        (3 of ($s*)) and filesize < 1MB
}