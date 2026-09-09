// SPDX-License-Identifier: Apache-2.0
package main

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

var externalDataRequired = map[string]bool{
	EventCultivation:         true,
	EventHarvest:             true,
	EventCollectionTransport: true,
	EventDistributionRetail:  true,
	EventResidueCustody:      true,
}

func validateExternalData(ctx contractapi.TransactionContextInterface, eventType, subjectID string, payload map[string]interface{}) error {
	if !externalDataRequired[eventType] {
		return nil
	}
	value, ok := payload["external_conditions"]
	if !ok {
		return fmt.Errorf("%s requires verified external_conditions fetched by the OliveChain oracle", eventType)
	}
	attestation, ok := value.(map[string]interface{})
	if !ok {
		return fmt.Errorf("external_conditions must be an oracle attestation object")
	}
	body, ok := attestation["body"].(map[string]interface{})
	if !ok {
		return fmt.Errorf("external_conditions.body is required")
	}
	signatureHex, ok := attestation["signature"].(string)
	if !ok || strings.TrimSpace(signatureHex) == "" {
		return fmt.Errorf("external_conditions.signature is required")
	}
	if trustedWeatherOraclePublicKeyHex == "__OLIVECHAIN_WEATHER_ORACLE_PUBLIC_KEY__" {
		return fmt.Errorf("weather oracle public key is not configured in this chaincode package")
	}
	if asString(body["type"]) != "olivechain-external-data-attestation" {
		return fmt.Errorf("unsupported external-data attestation type")
	}
	if asString(body["provider"]) != "open-meteo" {
		return fmt.Errorf("external-data provider is not approved")
	}
	if asString(body["event_type"]) != eventType {
		return fmt.Errorf("external-data attestation was issued for event %q, not %q", asString(body["event_type"]), eventType)
	}
	if asString(body["subject_id"]) != subjectID {
		return fmt.Errorf("external-data attestation was issued for subject %q, not %q", asString(body["subject_id"]), subjectID)
	}
	if asString(body["public_key"]) != trustedWeatherOraclePublicKeyHex {
		return fmt.Errorf("external-data attestation uses an untrusted oracle key")
	}
	if len(asString(body["raw_sha256"])) != 64 {
		return fmt.Errorf("external-data attestation is missing a valid raw response hash")
	}
	if strings.TrimSpace(asString(body["observed_at"])) == "" {
		return fmt.Errorf("external-data attestation is missing observed_at")
	}
	latitude, err := strconv.ParseFloat(asString(body["latitude"]), 64)
	if err != nil || latitude < -90 || latitude > 90 {
		return fmt.Errorf("external-data attestation has invalid latitude")
	}
	longitude, err := strconv.ParseFloat(asString(body["longitude"]), 64)
	if err != nil || longitude < -180 || longitude > 180 {
		return fmt.Errorf("external-data attestation has invalid longitude")
	}
	weather, ok := body["weather"].(map[string]interface{})
	if !ok || strings.TrimSpace(asString(weather["temperature_2m"])) == "" {
		return fmt.Errorf("external-data attestation is missing ambient temperature")
	}
	fetchedAt, ok := jsonNumberToInt64(body["fetched_at"])
	if !ok {
		return fmt.Errorf("external-data attestation has invalid fetched_at")
	}
	expiresAt, ok := jsonNumberToInt64(body["expires_at"])
	if !ok || expiresAt <= fetchedAt {
		return fmt.Errorf("external-data attestation has invalid expires_at")
	}
	stamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil || stamp == nil {
		return fmt.Errorf("cannot verify oracle freshness against transaction time")
	}
	txUnix := stamp.AsTime().Unix()
	if fetchedAt > txUnix+300 {
		return fmt.Errorf("external-data attestation appears to come from the future")
	}
	if txUnix > expiresAt {
		return fmt.Errorf("external-data attestation expired before transaction endorsement; fetch conditions again")
	}
	publicKey, err := hex.DecodeString(trustedWeatherOraclePublicKeyHex)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return fmt.Errorf("configured weather oracle public key is invalid")
	}
	signature, err := hex.DecodeString(signatureHex)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return fmt.Errorf("external-data attestation signature is malformed")
	}
	encodedBody, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("encode external-data attestation: %w", err)
	}
	if !ed25519.Verify(ed25519.PublicKey(publicKey), encodedBody, signature) {
		return fmt.Errorf("external-data attestation signature verification failed")
	}
	return nil
}

func jsonNumberToInt64(value interface{}) (int64, bool) {
	switch v := value.(type) {
	case float64:
		return int64(v), v == float64(int64(v))
	case json.Number:
		n, err := v.Int64()
		return n, err == nil
	case int:
		return int64(v), true
	case int64:
		return v, true
	default:
		return 0, false
	}
}
